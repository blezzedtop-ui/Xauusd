#property strict
#property version "1.2"
#property description "XAUUSD + EURUSD Railway <-> Exness MT5 DEMO bridge"
#include <Trade/Trade.mqh>
CTrade trade;

input string ApiBase="https://signalx.asia";
input string BridgeToken="SignalX_MT5_2026_9Kx7P2mQ";
input int PollSeconds=2;
input int StateSeconds=5;
input double DefaultLot=0.01;
input string TradeSymbol=""; // Optional legacy override; leave empty for dual-symbol routing
input string XAUTradeSymbol="XAUUSDm"; // Exness XAUUSD symbol
input string EURTradeSymbol="EURUSDm"; // Exness EURUSD symbol

string Url(string path){ return ApiBase+path; }
datetime g_last_state=0;
string JsonEscape(string s){ StringReplace(s,"\\","\\\\"); StringReplace(s,"\"","\\\""); return s; }
string ExecSymbol(){ string s=TradeSymbol; if(StringLen(s)==0) s=_Symbol; return s; }
string XAUStateSymbol(){ return XAUTradeSymbol; }
string EURStateSymbol(){ return EURTradeSymbol; }
string TFKey(ENUM_TIMEFRAMES tf){
   if(tf==PERIOD_M1) return "1min";
   if(tf==PERIOD_M5) return "5min";
   if(tf==PERIOD_M15) return "15min";
   if(tf==PERIOD_M30) return "30min";
   if(tf==PERIOD_H1) return "1h";
   if(tf==PERIOD_H4) return "4h";
   if(tf==PERIOD_D1) return "1day";
   return "";
}
string RatesJson(string symbol, ENUM_TIMEFRAMES tf, int count){
   MqlRates rates[];
   int copied=CopyRates(symbol,tf,0,count,rates);
   if(copied<=0) return "[]";
   int start=MathMax(0,copied-count);
   string out="["; bool first=true;
   for(int i=start;i<copied;i++){
      if(!first) out+=","; first=false;
      out += StringFormat("{\"time\":%I64d,\"open\":%.5f,\"high\":%.5f,\"low\":%.5f,\"close\":%.5f}",
         (long)rates[i].time,rates[i].open,rates[i].high,rates[i].low,rates[i].close);
   }
   out+="]"; return out;
}


int Http(string method,string url,string body,string &out){
   char data[]; if(StringLen(body)>0) StringToCharArray(body,data,0,StringLen(body),CP_UTF8);
   char result[]; string headers="Content-Type: application/json\r\n"; string result_headers="";
   ResetLastError();
   int code=WebRequest(method,url,headers,5000,data,result,result_headers);
   int err=GetLastError();
   out=CharArrayToString(result,0,-1,CP_UTF8);
   Print("[MT5 BRIDGE] ",method," ",url," -> HTTP=",code," LastError=",err," Response=",out);
   return code;
}

bool EnsureSymbol(string symbol){
   if(SymbolInfoDouble(symbol,SYMBOL_BID)<=0){
      if(!SymbolSelect(symbol,true)) return false;
   }
   return (SymbolInfoDouble(symbol,SYMBOL_BID)>0 || SymbolInfoDouble(symbol,SYMBOL_ASK)>0);
}

void AppendMarketState(string &body, string symbol, ENUM_TIMEFRAMES tfs[], int n, bool &firstMarket){
   if(!EnsureSymbol(symbol)) return;
   if(!firstMarket) body += ","; firstMarket=false;
   body += "\"" + JsonEscape(symbol) + "\":{";
   body += "\"connected\":true";
   body += ",\"account\":\"" + IntegerToString((long)AccountInfoInteger(ACCOUNT_LOGIN)) + "\"";
   body += ",\"server\":\"" + JsonEscape(AccountInfoString(ACCOUNT_SERVER)) + "\"";
   body += ",\"balance\":" + DoubleToString(AccountInfoDouble(ACCOUNT_BALANCE),2);
   body += ",\"equity\":" + DoubleToString(AccountInfoDouble(ACCOUNT_EQUITY),2);
   body += ",\"free_margin\":" + DoubleToString(AccountInfoDouble(ACCOUNT_MARGIN_FREE),2);
   body += ",\"margin\":" + DoubleToString(AccountInfoDouble(ACCOUNT_MARGIN),2);
   body += ",\"positions\":" + IntegerToString(PositionsTotal());
   body += ",\"candles\":{";
   for(int i=0;i<n;i++){
      if(i>0) body+=","; string k=TFKey(tfs[i]);
      body += "\""+k+"\":"+RatesJson(symbol,tfs[i],120);
   }
   body += "}}";
}

void ReportState(){
   ENUM_TIMEFRAMES tfs[6]={PERIOD_M5,PERIOD_M15,PERIOD_M30,PERIOD_H1,PERIOD_H4,PERIOD_D1};
   string body="{";
   body += "\"connected\":true";
   body += ",\"symbol\":\"XAUUSDm\"";
   body += ",\"login\":\"" + IntegerToString((long)AccountInfoInteger(ACCOUNT_LOGIN)) + "\"";
   body += ",\"server\":\"" + JsonEscape(AccountInfoString(ACCOUNT_SERVER)) + "\"";
   body += ",\"balance\":" + DoubleToString(AccountInfoDouble(ACCOUNT_BALANCE),2);
   body += ",\"equity\":" + DoubleToString(AccountInfoDouble(ACCOUNT_EQUITY),2);
   body += ",\"free_margin\":" + DoubleToString(AccountInfoDouble(ACCOUNT_MARGIN_FREE),2);
   body += ",\"margin\":" + DoubleToString(AccountInfoDouble(ACCOUNT_MARGIN),2);
   body += ",\"positions\":" + IntegerToString(PositionsTotal());
   body += ",\"candles\":{}";
   body += ",\"markets\":{";
   bool firstMarket=true;
   AppendMarketState(body,XAUStateSymbol(),tfs,6,firstMarket);
   AppendMarketState(body,EURStateSymbol(),tfs,6,firstMarket);
   body += "}}";
   Print("[MT5 BRIDGE] DUAL STATE BODY size=",StringLen(body));
   string out; Http("POST",Url("/api/v1/mt5/state?token="+BridgeToken),body,out);
}

string ExtractString(string json,string key,int from_pos){
   string needle="\""+key+"\":\""; int p=StringFind(json,needle,from_pos); if(p<0) return "";
   int s=p+StringLen(needle), e=StringFind(json,"\"",s); if(e<0) return "";
   return StringSubstr(json,s,e-s);
}

double ExtractNumber(string json,string key,int from_pos){
   string needle="\""+key+"\":"; int p=StringFind(json,needle,from_pos); if(p<0) return 0;
   int s=p+StringLen(needle), e=s;
   while(e<StringLen(json)){
      ushort c=StringGetCharacter(json,e);
      if((c>='0' && c<='9') || c=='-' || c=='+' || c=='.' || c=='e' || c=='E') e++; else break;
   }
   return StringToDouble(StringSubstr(json,s,e-s));
}

double ExtractFirstTP(string json,int from_pos){
   int p=StringFind(json,"\"tp\":[",from_pos); if(p<0) return 0;
   int s=p+StringLen("\"tp\":["), e=s;
   while(e<StringLen(json)){
      ushort c=StringGetCharacter(json,e);
      if((c>='0' && c<='9') || c=='-' || c=='+' || c=='.' || c=='e' || c=='E') e++; else break;
   }
   return StringToDouble(StringSubstr(json,s,e-s));
}

double NormalizePrice(string symbol,double price){
   int digits=(int)SymbolInfoInteger(symbol,SYMBOL_DIGITS);
   return NormalizeDouble(price,digits);
}

double MinStopDistance(string symbol){
   long stops=(long)SymbolInfoInteger(symbol,SYMBOL_TRADE_STOPS_LEVEL);
   long freeze=(long)SymbolInfoInteger(symbol,SYMBOL_TRADE_FREEZE_LEVEL);
   long level=MathMax(stops,freeze);
   double point=SymbolInfoDouble(symbol,SYMBOL_POINT);
   double spread=MathAbs(SymbolInfoDouble(symbol,SYMBOL_ASK)-SymbolInfoDouble(symbol,SYMBOL_BID));
   // Add a small safety buffer above the broker's minimum distance.
   return MathMax(point*(double)(level+5),spread*1.5);
}

bool PrepareStops(string symbol,string dir,double &sl,double &tp){
   double bid=SymbolInfoDouble(symbol,SYMBOL_BID);
   double ask=SymbolInfoDouble(symbol,SYMBOL_ASK);
   if(bid<=0 || ask<=0) return false;
   double entry=(dir=="BUY" ? ask : bid);
   double minDist=MinStopDistance(symbol);
   double risk=MathAbs(entry-sl);
   double target=MathAbs(tp-entry);
   // Some signal modules can emit levels from the wrong symbol/side. Keep the
   // signal when valid; otherwise rebuild a conservative market-relative SL/TP.
   bool valid=false;
   if(dir=="BUY") valid=(sl>0 && tp>0 && sl<entry-minDist && tp>entry+minDist);
   else if(dir=="SELL") valid=(sl>0 && tp>0 && sl>entry+minDist && tp<entry-minDist);
   if(!valid){
      double point=SymbolInfoDouble(symbol,SYMBOL_POINT);
      double fallback=MathMax(entry*0.0025,minDist*3.0);
      if(point>0) fallback=MathMax(fallback,point*20.0);
      risk=fallback;
      if(dir=="BUY"){
         sl=entry-risk;
         tp=entry-risk*2.0;
      }else{
         sl=entry+risk;
         tp=entry-risk*2.0;
      }
      Print("[MT5 BRIDGE] Invalid signal stops for ",symbol," ",dir," -> rebuilt SL/TP. Entry=",DoubleToString(entry,8));
   }else{
      // Revalidate the actual broker-side distance at execution time.
      if(risk<minDist) risk=minDist*1.2;
      if(target<minDist) target=minDist*1.2;
      if(dir=="BUY"){
         sl=MathMin(sl,entry-minDist);
         tp=MathMax(tp,entry+minDist);
      }else{
         sl=MathMax(sl,entry+minDist);
         tp=MathMin(tp,entry-minDist);
      }
   }
   sl=NormalizePrice(symbol,sl);
   tp=NormalizePrice(symbol,tp);
   // Final directional check after rounding.
   if(dir=="BUY") return (sl<entry-minDist && tp>entry+minDist);
   if(dir=="SELL") return (sl>entry+minDist && tp<entry-minDist);
   return false;
}

void SendReport(string order_id,string action,string status,string symbol,string message){
   string rb=StringFormat("{\"action\":\"%s\",\"ticket\":\"%s\",\"symbol\":\"%s\",\"status\":\"%s\",\"message\":\"%s\"}",
      JsonEscape(action),JsonEscape(order_id),JsonEscape(symbol),JsonEscape(status),JsonEscape(message));
   string out; Http("POST",Url("/api/v1/mt5/report?token="+BridgeToken),rb,out);
}

void OnInit(){
   Print("[MT5 BRIDGE] STARTED symbol=",_Symbol," ApiBase=",ApiBase," PollSeconds=",PollSeconds," Lot=",DoubleToString(DefaultLot,2));
   Print("[MT5 BRIDGE] If WebRequest is blocked, add this exact URL in Tools -> Options -> Expert Advisors: ",ApiBase);
   EventSetTimer(MathMax(1,PollSeconds));
}
void OnDeinit(const int reason){ EventKillTimer(); Print("[MT5 BRIDGE] STOPPED reason=",reason); }

void OnTimer(){
   if(g_last_state==0 || (TimeCurrent()-g_last_state)>=StateSeconds){ ReportState(); g_last_state=TimeCurrent(); }
   string out; int code=Http("GET",Url("/api/v1/mt5/poll?token="+BridgeToken),"",out);
   if(code!=200){ Print("[MT5 BRIDGE] POLL FAILED HTTP=",code," LastError=",GetLastError()); return; }
   if(StringFind(out,"\"orders\":[]")>=0){ Print("[MT5 BRIDGE] POLL OK - no queued orders"); return; }

   int pos=0;
   while((pos=StringFind(out,"\"id\":\"",pos))>=0){
      string order_id=ExtractString(out,"id",pos);
      string dir=ExtractString(out,"direction",pos);
      string requested_symbol=ExtractString(out,"symbol",pos);
      string source=ExtractString(out,"source",pos);
      double sl=ExtractNumber(out,"sl",pos);
      double tp=ExtractFirstTP(out,pos);
      double vol=ExtractNumber(out,"volume",pos); if(vol<=0) vol=DefaultLot;
      // One EA instance routes both XAUUSD and EURUSD. Execution is NOT limited by chart symbol.
      string req=requested_symbol; StringToUpper(req);
      string symbol="";
      if(StringFind(req,"EURUSD")>=0) symbol=EURStateSymbol();
      else if(StringFind(req,"XAUUSD")>=0) symbol=XAUStateSymbol();
      else symbol=ExecSymbol();

      bool ok=false;
      if(!EnsureSymbol(symbol)){
         SendReport(order_id,dir,"ORDER_FAILED",symbol,"Symbol not available: "+symbol);
      } else {
         trade.SetAsyncMode(false);
         string comment="SignalX "+(source==""?"AUTO":source);
         if((dir=="BUY" || dir=="SELL") && PrepareStops(symbol,dir,sl,tp)){
            if(dir=="BUY") ok=trade.Buy(vol,symbol,0,sl,tp,comment);
            else if(dir=="SELL") ok=trade.Sell(vol,symbol,0,sl,tp,comment);
         }else{
            Print("[MT5 BRIDGE] Invalid direction/stops; order skipped symbol=",symbol," dir=",dir);
         }
         string desc=trade.ResultRetcodeDescription();
         if(ok) SendReport(order_id,dir,"ORDER_SENT",symbol,desc);
         else SendReport(order_id,dir,"ORDER_FAILED",symbol,desc);
      }
      pos += MathMax(1,StringLen(order_id));
   }
}
