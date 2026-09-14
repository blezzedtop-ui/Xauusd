#property strict
#property version "1.3"
#property description "XAUUSD + EURUSD Railway <-> Exness MT5 DEMO bridge"
#include <Trade/Trade.mqh>
CTrade trade;

input string ApiBase="https://signalx.asia";
input string BridgeToken="SignalX_MT5_2026_9Kx7P2mQ";
input int PollSeconds=2;
input int StateSeconds=5;
input double DefaultLot=0.01;
input string TradeSymbol=""; // Optional legacy override; leave empty for dual-symbol routing
input string XAUTradeSymbol="XAUUSDm"; // Preferred XAUUSD broker symbol with suffix
input string XAUTradeSymbolNoSuffix="XAUUSD"; // XAUUSD broker symbol without suffix
input string EURTradeSymbol="EURUSDm"; // Preferred EURUSD broker symbol with suffix
input string EURTradeSymbolNoSuffix="EURUSD"; // EURUSD broker symbol without suffix

string Url(string path){ return ApiBase+path; }
datetime g_last_state=0;
string JsonEscape(string s){ StringReplace(s,"\\","\\\\"); StringReplace(s,"\"","\\\""); return s; }
string ExecSymbol(){ string s=TradeSymbol; if(StringLen(s)==0) s=_Symbol; return s; }
string FindAvailableVariant(string preferred,string noSuffix,string base){
   if(StringLen(preferred)>0 && SymbolInfoDouble(preferred,SYMBOL_BID)>0) return preferred;
   if(StringLen(noSuffix)>0 && SymbolInfoDouble(noSuffix,SYMBOL_BID)>0) return noSuffix;
   string needle=base; StringToUpper(needle);
   int total=SymbolsTotal(false);
   for(int i=0;i<total;i++){
      string name=SymbolName(i,false);
      string up=name; StringToUpper(up);
      if(StringFind(up,needle)>=0 && SymbolInfoDouble(name,SYMBOL_BID)>0) return name;
   }
   return preferred;
}
string XAUStateSymbol(){ return FindAvailableVariant(XAUTradeSymbol,XAUTradeSymbolNoSuffix,"XAUUSD"); }
string EURStateSymbol(){ return FindAvailableVariant(EURTradeSymbol,EURTradeSymbolNoSuffix,"EURUSD"); }
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
   return true;
}

void AppendMarketState(string &body, string symbol, ENUM_TIMEFRAMES &tfs[], int n, bool &firstMarket){
   if(!EnsureSymbol(symbol)) return;
   if(!firstMarket) body += ","; firstMarket=false;
   string marketKey = symbol;
   string upperMarket = symbol;
   StringToUpper(upperMarket);
   if(StringFind(upperMarket,"XAUUSD")>=0) marketKey="XAU/USD";
   else if(StringFind(upperMarket,"EURUSD")>=0) marketKey="EUR/USD";
   body += "\"" + JsonEscape(marketKey) + "\":{";
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
   // The top-level payload represents both markets; never label it as XAUUSD or EURUSD.
   body += ",\"symbol\":\"DUAL\"";
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

bool PollMarket(string requestedMarket, string expectedSymbol){
   string out;
   int code=Http("GET",Url("/api/v1/mt5/poll?token="+BridgeToken+"&market="+requestedMarket),"",out);
   if(code!=200){ Print("[MT5 BRIDGE] POLL FAILED market=",requestedMarket," HTTP=",code," LastError=",GetLastError()); return false; }
   if(StringFind(out,"\"orders\":[]")>=0){ Print("[MT5 BRIDGE] POLL OK market=",requestedMarket," - no queued orders"); return true; }

   int pos=0;
   while((pos=StringFind(out,"\"id\":\"",pos))>=0){
      string order_id=ExtractString(out,"id",pos);
      string dir=ExtractString(out,"direction",pos);
      string requested_symbol=ExtractString(out,"symbol",pos);
      string order_market=ExtractString(out,"market",pos);
      string source=ExtractString(out,"source",pos);
      double entry=ExtractNumber(out,"entry",pos);
      double sl=ExtractNumber(out,"sl",pos);
      double tp=ExtractFirstTP(out,pos);
      double vol=ExtractNumber(out,"volume",pos); if(vol<=0) vol=DefaultLot;

      // HARD SYMBOL BOUNDARY: server market filter + EA-side validation.
      string req=requested_symbol; StringToUpper(req);
      string marketCheck=order_market; StringToUpper(marketCheck);
      string expected=expectedSymbol; StringToUpper(expected);
      bool requestedIsEUR = (StringFind(requestedMarket,"EUR")>=0);
      bool marketMatches = requestedIsEUR ? (StringFind(marketCheck,"EUR")>=0) : (StringFind(marketCheck,"XAU")>=0);
      bool symbolMatches = requestedIsEUR ? (StringFind(req,"EURUSD")>=0) : (StringFind(req,"XAUUSD")>=0);
      if(!marketMatches || !symbolMatches){
         SendReport(order_id,dir,"ORDER_FAILED",expectedSymbol,"BLOCKED: cross-symbol order rejected by EA");
         pos += MathMax(1,StringLen(order_id));
         continue;
      }

      string execSymbol = requestedIsEUR
         ? FindAvailableVariant(EURTradeSymbol,EURTradeSymbolNoSuffix,"EURUSD")
         : FindAvailableVariant(XAUTradeSymbol,XAUTradeSymbolNoSuffix,"XAUUSD");
      bool ok=false;
      if(!EnsureSymbol(execSymbol)){
         SendReport(order_id,dir,"ORDER_FAILED",execSymbol,"Symbol not available (tried suffix and no-suffix variants)");
      } else {
         trade.SetAsyncMode(false);
         string comment="SignalX "+(source==""?"AUTO":source);
         if(dir=="BUY") ok=trade.Buy(vol,execSymbol,0,sl,tp,comment);
         else if(dir=="SELL") ok=trade.Sell(vol,execSymbol,0,sl,tp,comment);
         string desc=trade.ResultRetcodeDescription();
         if(ok) SendReport(order_id,dir,"ORDER_SENT",execSymbol,desc);
         else SendReport(order_id,dir,"ORDER_FAILED",execSymbol,desc);
      }
      pos += MathMax(1,StringLen(order_id));
   }
   return true;
}

void OnTimer(){
   if(g_last_state==0 || (TimeCurrent()-g_last_state)>=StateSeconds){ ReportState(); g_last_state=TimeCurrent(); }
   // Separate transport polls guarantee EURUSD orders never reach XAUUSD execution
   // and XAUUSD orders never reach EURUSD execution.
   PollMarket("XAU/USD", XAUStateSymbol());
   PollMarket("EUR/USD", EURStateSymbol());
}
