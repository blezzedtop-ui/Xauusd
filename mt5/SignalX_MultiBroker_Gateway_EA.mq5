#property strict
#property version "1.0"
#property description "SignalX Multi-Broker MT5 Account Gateway EA"

#include <Trade/Trade.mqh>
CTrade trade;

input string ApiBase="https://signalx.asia";
input string PairingCode="";
input int PollSeconds=2;
input int StateSeconds=5;
input double DefaultLot=0.01;
input long SignalXMagic=26091601;
input int MaxDeviationPoints=100;
input int MaxSpreadPoints=80;
input int ExecutionRetries=2;

string g_token="";
datetime g_last_poll=0, g_last_state=0;
bool g_registered=false;

string Url(string p){ return ApiBase+p; }

string JsonEscape(string s){
   StringReplace(s,"\\","\\\\");
   StringReplace(s,"\"","\\\"");
   StringReplace(s,"\r"," ");
   StringReplace(s,"\n"," ");
   return s;
}

string Compact(string s){
   StringToUpper(s);
   StringReplace(s,"/","");
   StringReplace(s,"-","");
   StringReplace(s,"_","");
   StringReplace(s,".","");
   return s;
}

string Canonical(string symbol){
   string c=Compact(symbol);
   if(StringFind(c,"XAUUSD")==0) return "XAU/USD";
   if(StringFind(c,"EURUSD")==0) return "EUR/USD";
   if(StringFind(c,"GBPUSD")==0) return "GBP/USD";
   return symbol;
}

bool IsUsable(string symbol){
   if(symbol=="") return false;
   if(SymbolInfoDouble(symbol,SYMBOL_BID)>0) return true;
   if(!SymbolSelect(symbol,true)) return false;
   return SymbolInfoDouble(symbol,SYMBOL_BID)>0;
}

string FindBrokerSymbol(string canonical){
   string target=Compact(canonical);
   int n=SymbolsTotal(false);
   for(int i=0;i<n;i++){
      string s=SymbolName(i,false);
      if(Compact(s)==target && IsUsable(s)) return s;
   }
   // suffix/prefix variants, but require the canonical compact code at the start.
   for(int i=0;i<n;i++){
      string s=SymbolName(i,false);
      string c=Compact(s);
      if((StringFind(c,target)==0 || StringFind(c,target)>0) && IsUsable(s)) return s;
   }
   return "";
}

string AccountType(){
   ENUM_ACCOUNT_TRADE_MODE m=(ENUM_ACCOUNT_TRADE_MODE)AccountInfoInteger(ACCOUNT_TRADE_MODE);
   if(m==ACCOUNT_TRADE_MODE_REAL) return "real";
   if(m==ACCOUNT_TRADE_MODE_DEMO) return "demo";
   return "contest";
}

string SymbolsJson(){
   string out="[";
   string canonicals[3]={"XAU/USD","EUR/USD","GBP/USD"};
   bool first=true;
   for(int i=0;i<3;i++){
      string broker=FindBrokerSymbol(canonicals[i]);
      if(broker=="") continue;
      if(!first) out+=",";
      first=false;
      int digits=(int)SymbolInfoInteger(broker,SYMBOL_DIGITS);
      double point=SymbolInfoDouble(broker,SYMBOL_POINT);
      double vmin=SymbolInfoDouble(broker,SYMBOL_VOLUME_MIN);
      double vstep=SymbolInfoDouble(broker,SYMBOL_VOLUME_STEP);
      double vmax=SymbolInfoDouble(broker,SYMBOL_VOLUME_MAX);
      long mode=SymbolInfoInteger(broker,SYMBOL_TRADE_MODE);
      out+="{\"canonical_symbol\":\""+canonicals[i]+"\",\"broker_symbol\":\""+JsonEscape(broker)+"\",\"digits\":"+IntegerToString(digits);
      out+=",\"point\":"+DoubleToString(point,10)+",\"volume_min\":"+DoubleToString(vmin,8);
      out+=",\"volume_step\":"+DoubleToString(vstep,8)+",\"volume_max\":"+DoubleToString(vmax,8);
      out+=",\"trade_mode\":\""+IntegerToString((int)mode)+"\"}";
   }
   out+="]";
   return out;
}

bool Http(string method,string path,string body,string &response){
   string headers="Content-Type: application/json\r\n";
   if(g_token!="") headers+="Authorization: Bearer "+g_token+"\r\n";
   char data[], result[];
   string result_headers;
   int data_len=StringToCharArray(body,data,0,WHOLE_ARRAY,CP_UTF8);
   // StringToCharArray(..., WHOLE_ARRAY, ...) appends a terminal NUL.
   // WebRequest must receive the JSON bytes without that NUL, otherwise
   // FastAPI/Python can reject an otherwise valid payload as "Extra data".
   if(data_len>0 && data[data_len-1]==0) data_len--;
   if(data_len<0) data_len=0;
   ArrayResize(data,data_len);
   ResetLastError();
   int code=WebRequest(method,Url(path),headers,8000,data,result,result_headers);
   if(code<0){
      Print("[SIGNALX GATEWAY] WebRequest error=",GetLastError()," path=",path);
      return false;
   }
   response=CharArrayToString(result,0,-1,CP_UTF8);
   if(code<200 || code>=300){
      Print("[SIGNALX GATEWAY] HTTP ",code," path=",path," body=",response);
      return false;
   }
   return true;
}

string JsonString(string json,string key){
   string needle="\""+key+"\":\"";
   int p=StringFind(json,needle);
   if(p<0) return "";
   p+=StringLen(needle);
   int e=StringFind(json,"\"",p);
   if(e<0) return "";
   return StringSubstr(json,p,e-p);
}

double JsonNumber(string json,string key){
   string needle="\""+key+"\":";
   int p=StringFind(json,needle);
   if(p<0) return 0;
   p+=StringLen(needle);
   int e=p;
   int n=StringLen(json);
   while(e<n){
      ushort ch=StringGetCharacter(json,e);
      if((ch>='0'&&ch<='9') || ch=='-' || ch=='.' || ch=='e' || ch=='E' || ch=='+') e++;
      else break;
   }
   return StringToDouble(StringSubstr(json,p,e-p));
}

bool JsonBool(string json,string key){
   string needle="\""+key+"\":";
   int p=StringFind(json,needle);
   if(p<0) return false;
   p+=StringLen(needle);
   return StringFind(StringSubstr(json,p,5),"true")==0;
}

bool Register(){
   if(StringLen(PairingCode)<6){
      Print("[SIGNALX GATEWAY] PairingCode is required.");
      return false;
   }
   string body="{\"pairing_code\":\""+JsonEscape(PairingCode)+"\"";
   body+=",\"broker\":\""+JsonEscape(AccountInfoString(ACCOUNT_COMPANY))+"\"";
   body+=",\"server\":\""+JsonEscape(AccountInfoString(ACCOUNT_SERVER))+"\"";
   body+=",\"login\":\""+IntegerToString((long)AccountInfoInteger(ACCOUNT_LOGIN))+"\"";
   body+=",\"account_type\":\""+AccountType()+"\"";
   body+=",\"currency\":\""+JsonEscape(AccountInfoString(ACCOUNT_CURRENCY))+"\"";
   body+=",\"leverage\":"+IntegerToString((int)AccountInfoInteger(ACCOUNT_LEVERAGE));
   body+=",\"balance\":"+DoubleToString(AccountInfoDouble(ACCOUNT_BALANCE),2);
   body+=",\"equity\":"+DoubleToString(AccountInfoDouble(ACCOUNT_EQUITY),2);
   body+=",\"free_margin\":"+DoubleToString(AccountInfoDouble(ACCOUNT_MARGIN_FREE),2);
   body+=",\"margin\":"+DoubleToString(AccountInfoDouble(ACCOUNT_MARGIN),2);
   body+=",\"trade_allowed\":"+(AccountInfoInteger(ACCOUNT_TRADE_ALLOWED)?"true":"false");
   body+=",\"terminal_build\":\""+IntegerToString((int)TerminalInfoInteger(TERMINAL_BUILD))+"\"";
   body+=",\"ea_version\":\"1.0\"";
   body+=",\"symbols\":"+SymbolsJson()+"}";
   string response;
   if(!Http("POST","/api/v1/mt5/gateway/register",body,response)) return false;
   g_token=JsonString(response,"account_token");
   g_registered=(StringLen(g_token)>20);
   if(g_registered) Print("[SIGNALX GATEWAY] REGISTERED login=",AccountInfoInteger(ACCOUNT_LOGIN)," server=",AccountInfoString(ACCOUNT_SERVER)," type=",AccountType());
   return g_registered;
}

bool SendState(){
   if(!g_registered) return false;
   string body="{\"broker\":\""+JsonEscape(AccountInfoString(ACCOUNT_COMPANY))+"\"";
   body+=",\"server\":\""+JsonEscape(AccountInfoString(ACCOUNT_SERVER))+"\"";
   body+=",\"login\":\""+IntegerToString((long)AccountInfoInteger(ACCOUNT_LOGIN))+"\"";
   body+=",\"account_type\":\""+AccountType()+"\",\"currency\":\""+JsonEscape(AccountInfoString(ACCOUNT_CURRENCY))+"\"";
   body+=",\"leverage\":"+IntegerToString((int)AccountInfoInteger(ACCOUNT_LEVERAGE));
   body+=",\"balance\":"+DoubleToString(AccountInfoDouble(ACCOUNT_BALANCE),2);
   body+=",\"equity\":"+DoubleToString(AccountInfoDouble(ACCOUNT_EQUITY),2);
   body+=",\"free_margin\":"+DoubleToString(AccountInfoDouble(ACCOUNT_MARGIN_FREE),2);
   body+=",\"margin\":"+DoubleToString(AccountInfoDouble(ACCOUNT_MARGIN),2);
   body+=",\"trade_allowed\":"+(AccountInfoInteger(ACCOUNT_TRADE_ALLOWED)?"true":"false");
   body+=",\"terminal_build\":\""+IntegerToString((int)TerminalInfoInteger(TERMINAL_BUILD))+"\",\"ea_version\":\"1.0\"";
   body+=",\"symbols\":"+SymbolsJson()+"}";
   string response;
   return Http("POST","/api/v1/mt5/gateway/state",body,response);
}

bool ParseAndExecute(string json){
   int p=StringFind(json,"\"orders\":[");
   if(p<0) return false;
   p=StringFind(json,"{",p);
   if(p<0) return false;
   int e=StringFind(json,"}",p);
   if(e<0) return false;
   string o=StringSubstr(json,p,e-p+1);
   string order_id=JsonString(o,"order_id");
   string symbol=JsonString(o,"execution_symbol");
   string direction=JsonString(o,"direction");
   double volume=JsonNumber(o,"volume");
   double sl=JsonNumber(o,"stop_loss");
   double tp=JsonNumber(o,"take_profit");
   if(order_id=="" || symbol=="" || (direction!="BUY" && direction!="SELL")) return false;
   if(!IsUsable(symbol)){
      string report="{\"order_id\":"+order_id+",\"status\":\"REJECTED\",\"broker_message\":\"Symbol unavailable: "+JsonEscape(symbol)+"\"}";
      string rr; Http("POST","/api/v1/mt5/gateway/report",report,rr); return false;
   }
   double bid=SymbolInfoDouble(symbol,SYMBOL_BID), ask=SymbolInfoDouble(symbol,SYMBOL_ASK);
   double point=SymbolInfoDouble(symbol,SYMBOL_POINT);
   if(point<=0) point=_Point;
   double spread=(ask-bid)/point;
   if(spread>MaxSpreadPoints){
      string report="{\"order_id\":"+order_id+",\"status\":\"REJECTED\",\"broker_message\":\"Spread guard\"}";
      string rr; Http("POST","/api/v1/mt5/gateway/report",report,rr); return false;
   }
   if(volume<=0) volume=DefaultLot;
   double vmin=SymbolInfoDouble(symbol,SYMBOL_VOLUME_MIN), vmax=SymbolInfoDouble(symbol,SYMBOL_VOLUME_MAX), vstep=SymbolInfoDouble(symbol,SYMBOL_VOLUME_STEP);
   if(vmin>0 && volume<vmin) volume=vmin;
   if(vmax>0 && volume>vmax) volume=vmax;
   if(vstep>0) volume=MathFloor(volume/vstep)*vstep;
   trade.SetExpertMagicNumber(SignalXMagic);
   trade.SetDeviationInPoints(MaxDeviationPoints);
   bool sent=false;
   string last="";
   for(int attempt=0;attempt<=ExecutionRetries && !sent;attempt++){
      ResetLastError();
      if(direction=="BUY") sent=trade.Buy(volume,symbol,0,sl,tp,"SignalX "+order_id);
      else sent=trade.Sell(volume,symbol,0,sl,tp,"SignalX "+order_id);
      if(!sent) last=trade.ResultRetcodeDescription();
      if(!sent) Sleep(300);
   }
   ulong deal_ticket=trade.ResultDeal();
   ulong order_ticket=trade.ResultOrder();
   string status=!sent?"FAILED":(deal_ticket>0?"FILLED":"SENT");
   string report="{\"order_id\":"+order_id+",\"status\":\""+status+"\",\"broker_ticket\":\""+IntegerToString((long)(deal_ticket>0?deal_ticket:order_ticket));
   report+="\",\"broker_retcode\":\""+IntegerToString((int)trade.ResultRetcode())+"\",\"broker_message\":\""+JsonEscape(sent?"ORDER_SENT":last)+"\"}";
   string rr; Http("POST","/api/v1/mt5/gateway/report",report,rr);
   Print("[SIGNALX GATEWAY] ",status," order=",order_id," symbol=",symbol," direction=",direction," volume=",DoubleToString(volume,2));
   return sent;
}

void Poll(){
   if(!g_registered) return;
   string response;
   if(Http("GET","/api/v1/mt5/gateway/poll","",response)) ParseAndExecute(response);
}

int OnInit(){
   EventSetTimer(1);
   if(!Register()) Print("[SIGNALX GATEWAY] Waiting for valid pairing code / WebRequest permission.");
   return INIT_SUCCEEDED;
}

void OnDeinit(const int reason){ EventKillTimer(); }

void OnTimer(){
   datetime now=TimeCurrent();
   if(!g_registered && StringLen(PairingCode)>=6) Register();
   if(g_registered && (now-g_last_state)>=StateSeconds){ SendState(); g_last_state=now; }
   if(g_registered && (now-g_last_poll)>=PollSeconds){ Poll(); g_last_poll=now; }
}
