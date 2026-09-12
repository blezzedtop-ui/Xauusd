#property strict
#property version "2.0"
#property description "Multi-symbol XAUUSDm + EURUSDm Railway <-> Exness MT5 DEMO bridge"
#include <Trade/Trade.mqh>
CTrade trade;

input string ApiBase="https://YOUR-RAILWAY-DOMAIN";
input string BridgeToken="CHANGE_ME";
input string Symbol1="XAUUSDm";
input string Symbol2="EURUSDm";
input int PollSeconds=2;
input int StateSeconds=5;
input double DefaultLot=0.01;

string Url(string path){ return ApiBase+path; }
datetime g_last_state=0;
string JsonEscape(string s){ StringReplace(s,"\\","\\\\"); StringReplace(s,"\"","\\\""); return s; }
string TFKey(ENUM_TIMEFRAMES tf){
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
   string out="["; bool first=true;
   for(int i=0;i<copied;i++){
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
   if(!SymbolSelect(symbol,true)) return false;
   return SymbolInfoDouble(symbol,SYMBOL_BID)>0 || SymbolInfoDouble(symbol,SYMBOL_ASK)>0;
}
void ReportState(string symbol){
   if(!EnsureSymbol(symbol)) { Print("[MT5 BRIDGE] Symbol unavailable: ",symbol); return; }
   string body="{";
   body += "\"symbol\":\"" + JsonEscape(symbol) + "\"";
   body += ",\"connected\":true";
   body += ",\"login\":\"" + IntegerToString((long)AccountInfoInteger(ACCOUNT_LOGIN)) + "\"";
   body += ",\"server\":\"" + JsonEscape(AccountInfoString(ACCOUNT_SERVER)) + "\"";
   body += ",\"balance\":" + DoubleToString(AccountInfoDouble(ACCOUNT_BALANCE),2);
   body += ",\"equity\":" + DoubleToString(AccountInfoDouble(ACCOUNT_EQUITY),2);
   body += ",\"free_margin\":" + DoubleToString(AccountInfoDouble(ACCOUNT_MARGIN_FREE),2);
   body += ",\"margin\":" + DoubleToString(AccountInfoDouble(ACCOUNT_MARGIN),2);
   body += ",\"positions\":" + IntegerToString(PositionsTotal());
   body += ",\"candles\":{";
   ENUM_TIMEFRAMES tfs[6]={PERIOD_M5,PERIOD_M15,PERIOD_M30,PERIOD_H1,PERIOD_H4,PERIOD_D1};
   for(int i=0;i<6;i++){ if(i>0) body+=","; string k=TFKey(tfs[i]); body += "\""+k+"\":"+RatesJson(symbol,tfs[i],120); }
   body += "}}";
   string out; Http("POST",Url("/api/v1/mt5/state?token="+BridgeToken),body,out);
}
string ExtractString(string json,string key,int &pos){
   string needle="\""+key+"\":"; pos=StringFind(json,needle,pos); if(pos<0) return ""; pos+=StringLen(needle);
   if(StringGetCharacter(json,pos)=='\"'){ pos++; int end=StringFind(json,"\"",pos); if(end<0) return ""; string s=StringSubstr(json,pos,end-pos); pos=end+1; return s; }
   int end=StringFind(json,",",pos); if(end<0) end=StringFind(json,"}",pos); if(end<0) end=StringLen(json); string s=StringSubstr(json,pos,end-pos); pos=end; return s;
}
double ExtractNumber(string json,string key){ int p=0; string s=ExtractString(json,key,p); return StringToDouble(s); }
void SendReport(string order_id,string action,string status,string symbol,string message){
   string rb=StringFormat("{\"action\":\"%s\",\"ticket\":\"%s\",\"symbol\":\"%s\",\"status\":\"%s\",\"message\":\"%s\"}",
      JsonEscape(action),JsonEscape(order_id),JsonEscape(symbol),JsonEscape(status),JsonEscape(message));
   string out; Http("POST",Url("/api/v1/mt5/report?token="+BridgeToken),rb,out);
}
void PollOrders(){
   string out; int code=Http("GET",Url("/api/v1/mt5/poll?token="+BridgeToken),"",out); if(code<200||code>=300) return;
   int p=0;
   while(true){
      int idp=StringFind(out,"\"id\":\"",p); if(idp<0) break; idp+=7; int ide=StringFind(out,"\"",idp); if(ide<0) break; string order_id=StringSubstr(out,idp,ide-idp); p=ide+1;
      int symp=StringFind(out,"\"symbol\":\"",p); if(symp<0) break; symp+=10; int syme=StringFind(out,"\"",symp); if(syme<0) break; string symbol=StringSubstr(out,symp,syme-symp); p=syme+1;
      int dirp=StringFind(out,"\"direction\":\"",p); if(dirp<0) break; dirp+=14; int dire=StringFind(out,"\"",dirp); if(dire<0) break; string dir=StringSubstr(out,dirp,dire-dirp); p=dire+1;
      int slp=StringFind(out,"\"sl\":",p); if(slp<0) break; slp+=5; int sle=StringFind(out,",",slp); double sl=StringToDouble(StringSubstr(out,slp,sle-slp)); p=sle+1;
      int tpp=StringFind(out,"\"tp\":[",p); if(tpp<0) break; tpp+=7; int tpe=StringFind(out,",",tpp); if(tpe<0) tpe=StringFind(out,"]",tpp); double tp=StringToDouble(StringSubstr(out,tpp,tpe-tpp)); p=tpe+1;
      double vol=DefaultLot;
      if(!EnsureSymbol(symbol)){ SendReport(order_id,dir,"ORDER_FAILED",symbol,"Symbol not available: "+symbol); continue; }
      bool ok=false;
      if(dir=="BUY") ok=trade.Buy(vol,symbol,0,sl,tp,"AI Strong Zone");
      else if(dir=="SELL") ok=trade.Sell(vol,symbol,0,sl,tp,"AI Strong Zone");
      if(ok) SendReport(order_id,dir,"ORDER_SENT",symbol,"Order sent by multi-symbol EA");
      else SendReport(order_id,dir,"ORDER_FAILED",symbol,"MT5 trade error: "+trade.ResultRetcodeDescription());
   }
}
int OnInit(){
   EventSetTimer(1);
   EnsureSymbol(Symbol1); EnsureSymbol(Symbol2);
   Print("[MT5 BRIDGE] MULTI STARTED: ",Symbol1," + ",Symbol2," ApiBase=",ApiBase);
   Print("[MT5 BRIDGE] Add URL in Tools -> Options -> Expert Advisors: ",ApiBase);
   return INIT_SUCCEEDED;
}
void OnDeinit(const int reason){ EventKillTimer(); }
void OnTimer(){
   static int sec=0; sec++;
   if(sec>=StateSeconds){ sec=0; ReportState(Symbol1); ReportState(Symbol2); }
   PollOrders();
}
