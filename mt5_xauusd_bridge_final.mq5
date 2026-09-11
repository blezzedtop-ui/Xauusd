#property strict
#property version "1.1"
#property description "XAUUSD Railway <-> Exness MT5 DEMO bridge"
#include <Trade/Trade.mqh>
CTrade trade;

input string ApiBase="https://xauusd-production-9fd9.up.railway.app";
input string BridgeToken="MT5-XAUUSD-DEMO-9f7K2mQ8vL4xP6sR1zN5";
input int PollSeconds=2;
input double DefaultLot=0.01;
input string TradeSymbol=""; // Leave empty: use the chart symbol (e.g. XAUUSDm on Exness)

string Url(string path){ return ApiBase+path; }
string JsonEscape(string s){ StringReplace(s,"\\","\\\\"); StringReplace(s,"\"","\\\""); return s; }
string ExecSymbol(){ string s=TradeSymbol; if(StringLen(s)==0) s=_Symbol; return s; }

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
   string body="{";
   body += "\"connected\":true";
   body += ",\"login\":\"" + IntegerToString((long)AccountInfoInteger(ACCOUNT_LOGIN)) + "\"";
   body += ",\"server\":\"" + JsonEscape(AccountInfoString(ACCOUNT_SERVER)) + "\"";
   body += ",\"balance\":" + DoubleToString(AccountInfoDouble(ACCOUNT_BALANCE),2);
   body += ",\"equity\":" + DoubleToString(AccountInfoDouble(ACCOUNT_EQUITY),2);
   body += ",\"free_margin\":" + DoubleToString(AccountInfoDouble(ACCOUNT_MARGIN_FREE),2);
   body += ",\"margin\":" + DoubleToString(AccountInfoDouble(ACCOUNT_MARGIN),2);
   body += ",\"positions\":" + IntegerToString(PositionsTotal());
   body += "}";
   Print("[MT5 BRIDGE] STATE BODY=",body);
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
   ReportState();
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
      if(StringLen(requested_symbol)>0 && StringFind(requested_symbol,"XAUUSD")>=0) symbol=ExecSymbol();

      bool ok=false;
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
