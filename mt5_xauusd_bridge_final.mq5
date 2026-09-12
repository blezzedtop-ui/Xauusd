#property strict
#property version "1.2"
#property description "XAUUSD Railway <-> Exness MT5 DEMO bridge"
#include <Trade/Trade.mqh>
CTrade trade;

input string ApiBase="https://YOUR-RAILWAY-DOMAIN";
input string BridgeToken="CHANGE_ME";
input int PollSeconds=2;
input int StateSeconds=5;
input double DefaultLot=0.01;
input string TradeSymbol=""; // Leave empty: use the chart symbol (e.g. XAUUSDm on Exness)

string Url(string path){ return ApiBase+path; }
datetime g_last_state=0;
string JsonEscape(string s){ StringReplace(s,"\\","\\\\"); StringReplace(s,"\"","\\\""); return s; }
string ExecSymbol(){ string s=TradeSymbol; if(StringLen(s)==0) s=_Symbol; return s; }
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

void ReportState(){
   string symbol=ExecSymbol();
   string body="{";
   body += "\"connected\":true";
   body += ",\"symbol\":\"" + JsonEscape(symbol) + "\"";
   body += ",\"login\":\"" + IntegerToString((long)AccountInfoInteger(ACCOUNT_LOGIN)) + "\"";
   body += ",\"server\":\"" + JsonEscape(AccountInfoString(ACCOUNT_SERVER)) + "\"";
   body += ",\"balance\":" + DoubleToString(AccountInfoDouble(ACCOUNT_BALANCE),2);
   body += ",\"equity\":" + DoubleToString(AccountInfoDouble(ACCOUNT_EQUITY),2);
   body += ",\"free_margin\":" + DoubleToString(AccountInfoDouble(ACCOUNT_MARGIN_FREE),2);
   body += ",\"margin\":" + DoubleToString(AccountInfoDouble(ACCOUNT_MARGIN),2);
   body += ",\"positions\":" + IntegerToString(PositionsTotal());
   body += ",\"candles\":{";
   ENUM_TIMEFRAMES tfs[6]={PERIOD_M5,PERIOD_M15,PERIOD_M30,PERIOD_H1,PERIOD_H4,PERIOD_D1};
   for(int i=0;i<6;i++){
      if(i>0) body+=","; string k=TFKey(tfs[i]);
      body += "\""+k+"\":"+RatesJson(symbol,tfs[i],120);
   }
   body += "}}";
   Print("[MT5 BRIDGE] STATE BODY size=",StringLen(body));
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
      double sl=ExtractNumber(out,"sl",pos);
      double tp=ExtractFirstTP(out,pos);
      double vol=ExtractNumber(out,"volume",pos); if(vol<=0) vol=DefaultLot;
      string symbol=ExecSymbol();
      string req=StringUpper(requested_symbol);
      string chart=StringUpper(symbol);
      bool requested_matches_chart=(StringLen(req)==0) || ((StringFind(req,"XAUUSD")>=0 && StringFind(chart,"XAUUSD")>=0) || (StringFind(req,"EURUSD")>=0 && StringFind(chart,"EURUSD")>=0));

      bool ok=false;
      if(!requested_matches_chart){
         SendReport(order_id,dir,"ORDER_FAILED",symbol,"Queued symbol mismatch: requested="+requested_symbol+" chart="+symbol);
         pos += MathMax(1,StringLen(order_id));
         continue;
      }
      if(!EnsureSymbol(symbol)){
         SendReport(order_id,dir,"ORDER_FAILED",symbol,"Symbol not available: "+symbol);
      } else {
         trade.SetAsyncMode(false);
         if(dir=="BUY") ok=trade.Buy(vol,symbol,0,sl,tp,"AI Strong Zone");
         else if(dir=="SELL") ok=trade.Sell(vol,symbol,0,sl,tp,"AI Strong Zone");
         string desc=trade.ResultRetcodeDescription();
         if(ok) SendReport(order_id,dir,"ORDER_SENT",symbol,desc);
         else SendReport(order_id,dir,"ORDER_FAILED",symbol,desc);
      }
      pos += MathMax(1,StringLen(order_id));
   }
}
