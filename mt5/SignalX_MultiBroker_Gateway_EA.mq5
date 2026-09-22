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
input string XAUTradeSymbol="XAUUSDm";
input int DuplicateCooldownSeconds=30;
input int MaxOpenPositionsPerSymbol=3; // Aggregate limit across all nine modules

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
      if(StringFind(c,target)>=0 && IsUsable(s)) return s;
   }
   return "";
}

string AccountType(){
   ENUM_ACCOUNT_TRADE_MODE m=(ENUM_ACCOUNT_TRADE_MODE)AccountInfoInteger(ACCOUNT_TRADE_MODE);
   if(m==ACCOUNT_TRADE_MODE_REAL) return "real";
   if(m==ACCOUNT_TRADE_MODE_DEMO) return "demo";
   return "contest";
}

bool SymbolSessionOpenNow(string symbol, string &source)
{
   source="MT5_SYMBOL_TRADE_SESSION";
   if(symbol=="") return false;
   datetime now=TimeTradeServer();
   if(now<=0) now=TimeCurrent();
   MqlDateTime dt;
   TimeToStruct(now,dt);
   int current_min=dt.hour*60+dt.min;
   ENUM_DAY_OF_WEEK dow=(ENUM_DAY_OF_WEEK)dt.day_of_week;
   bool found=false;
   for(uint i=0;i<20;i++)
   {
      datetime from=0,to=0;
      ResetLastError();
      if(!SymbolInfoSessionTrade(symbol,dow,i,from,to)) break;
      found=true;
      int from_min=TimeHour(from)*60+TimeMinute(from);
      int to_min=TimeHour(to)*60+TimeMinute(to);
      bool open=false;
      if(from_min<=to_min)
         open=(current_min>=from_min && current_min<to_min);
      else
         open=(current_min>=from_min || current_min<to_min);
      if(open) return true;
   }
   return false;
}

string SessionStateJson(string symbol)
{
   string source="MT5_SYMBOL_TRADE_SESSION";
   bool open=SymbolSessionOpenNow(symbol,source);
   datetime now=TimeTradeServer();
   if(now<=0) now=TimeCurrent();
   string out=",\"session_open\":"+(open?"true":"false");
   out+=",\"session_source\":\""+JsonEscape(source)+"\"";
   out+=",\"server_time\":\""+JsonEscape(TimeToString(now,TIME_DATE|TIME_SECONDS))+"\"";
   return out;
}

bool IsUsableSymbol(string symbol)
{
   if(StringLen(symbol)==0) return false;
   if(SymbolInfoDouble(symbol,SYMBOL_BID)>0) return true;
   if(!SymbolSelect(symbol,true)) return false;
   return (SymbolInfoDouble(symbol,SYMBOL_BID)>0);
}

bool IsExactAllowedSymbol(string symbol)
{
   // Multi-broker XAU/USD guard: accept broker-specific suffix/prefix variants
   // while refusing unrelated instruments.
   return (Canonical(symbol)=="XAU/USD");
}

double NormalizePrice(string symbol,double price)
{
   double tick_size=SymbolInfoDouble(symbol,SYMBOL_TRADE_TICK_SIZE);
   if(tick_size<=0) tick_size=SymbolInfoDouble(symbol,SYMBOL_POINT);
   if(tick_size<=0) return price;
   return NormalizeDouble(MathRound(price/tick_size)*tick_size,(int)SymbolInfoInteger(symbol,SYMBOL_DIGITS));
}

bool IsBlockedSource(string source)
{
   string x=source;
   StringToLower(x);
   StringTrimLeft(x); StringTrimRight(x);
   return !(x=="ict ai pro" || x=="snr" || x=="ai analysis" || x=="trend" ||
            x=="trend liniya" || x=="technical analysis" || x=="classic trade" ||
            x=="ob trade" || x=="fibonacci trade");
}

bool ValidExecutionRR(string symbol,string direction,string orderType,double entry,double sl,double tp)
{
   MqlTick tick;
   if(!SymbolInfoTick(symbol,tick)) return false;
   double point=SymbolInfoDouble(symbol,SYMBOL_POINT);
   double fill=entry;
   if(orderType=="MARKET")
      fill=(direction=="BUY" ? tick.ask+MaxDeviationPoints*point : tick.bid-MaxDeviationPoints*point);
   if(!MathIsValidNumber(fill) || !MathIsValidNumber(sl) || !MathIsValidNumber(tp) || fill<=0 || sl<=0 || tp<=0) return false;
   double risk=(direction=="BUY" ? fill-sl : sl-fill);
   double reward=(direction=="BUY" ? tp-fill : fill-tp);
   return (risk>0 && reward>0 && reward/risk>=1.0-0.00000001);
}

string OrderGuardKey(string order_id)
{
   return "SignalX.guard."+IntegerToString((long)AccountInfoInteger(ACCOUNT_LOGIN))+"."+order_id;
}

bool GuardAllows(string order_id)
{
   if(order_id=="") return false;
   if(GlobalVariableCheck(OrderGuardKey(order_id)+".done")) return false;
   string key=OrderGuardKey(order_id);
   if(!GlobalVariableCheck(key)) return true;
   double last=GlobalVariableGet(key);
   return (TimeCurrent()-((datetime)last)) >= DuplicateCooldownSeconds;
}

void MarkOrderGuard(string order_id)
{
   if(order_id!="") GlobalVariableSet(OrderGuardKey(order_id),(double)TimeCurrent());
}


int CountSignalXPositions(string symbol)
{
   int count=0;
   for(int i=0;i<PositionsTotal();i++)
   {
      ulong ticket=PositionGetTicket(i);
      if(ticket==0 || !PositionSelectByTicket(ticket)) continue;
      string ps=PositionGetString(POSITION_SYMBOL);
      long magic=PositionGetInteger(POSITION_MAGIC);
      if(ps==symbol && magic==SignalXMagic) count++;
   }
   return count;
}

bool HasEnoughMargin(string symbol,string dir,double volume)
{
   MqlTick tick;
   if(!SymbolInfoTick(symbol,tick)) return false;
   double margin=0.0;
   ENUM_ORDER_TYPE type=(dir=="BUY" ? ORDER_TYPE_BUY : ORDER_TYPE_SELL);
   double price=(dir=="BUY" ? tick.ask : tick.bid);
   if(!OrderCalcMargin(type,symbol,volume,price,margin)) return false;
   double free=AccountInfoDouble(ACCOUNT_MARGIN_FREE);
   return (margin>0.0 && free>=margin);
}

bool IsTransientRetcode(uint retcode)
{
   return (retcode==TRADE_RETCODE_REQUOTE ||
           retcode==TRADE_RETCODE_PRICE_CHANGED ||
           retcode==TRADE_RETCODE_PRICE_OFF ||
           retcode==TRADE_RETCODE_TOO_MANY_REQUESTS);
}

bool ValidSignalLevels(string symbol,string dir,double sl,double tp)
{
   if(!IsExactAllowedSymbol(symbol) || !IsUsableSymbol(symbol)) return false;
   if(sl<=0 || tp<=0 || !MathIsValidNumber(sl) || !MathIsValidNumber(tp)) return false;
   sl=NormalizePrice(symbol,sl);
   tp=NormalizePrice(symbol,tp);
   MqlTick tick;
   if(!SymbolInfoTick(symbol,tick)) return false;
   double point=SymbolInfoDouble(symbol,SYMBOL_POINT);
   double tick_size=SymbolInfoDouble(symbol,SYMBOL_TRADE_TICK_SIZE);
   if(tick_size<=0) tick_size=point;
   int stops=(int)SymbolInfoInteger(symbol,SYMBOL_TRADE_STOPS_LEVEL);
   int freeze=(int)SymbolInfoInteger(symbol,SYMBOL_TRADE_FREEZE_LEVEL);
   double minDist=MathMax(stops,freeze)*point;
   if(minDist<tick_size) minDist=tick_size;
   if(dir=="BUY") return (sl <= tick.bid-minDist && tp >= tick.ask+minDist);
   if(dir=="SELL") return (sl >= tick.ask+minDist && tp <= tick.bid-minDist);
   return false;
}

bool IsPendingOrderType(string orderType)
{
   return orderType=="BUY_STOP" || orderType=="SELL_STOP" ||
          orderType=="BUY_LIMIT" || orderType=="SELL_LIMIT";
}

bool PendingEntryValid(string symbol,string orderType,double entry)
{
   if(!IsPendingOrderType(orderType) || entry<=0 || !MathIsValidNumber(entry)) return false;
   MqlTick tick;
   if(!SymbolInfoTick(symbol,tick)) return false;
   double point=SymbolInfoDouble(symbol,SYMBOL_POINT);
   double tickSize=SymbolInfoDouble(symbol,SYMBOL_TRADE_TICK_SIZE);
   if(point<=0) return false;
   if(tickSize<=0) tickSize=point;
   entry=NormalizePrice(symbol,entry);
   int stops=(int)SymbolInfoInteger(symbol,SYMBOL_TRADE_STOPS_LEVEL);
   int freeze=(int)SymbolInfoInteger(symbol,SYMBOL_TRADE_FREEZE_LEVEL);
   double minDist=MathMax(stops,freeze)*point;
   if(minDist<tickSize) minDist=tickSize;
   if(orderType=="BUY_STOP")  return entry >= tick.ask + minDist;
   if(orderType=="SELL_STOP") return entry <= tick.bid - minDist;
   if(orderType=="BUY_LIMIT") return entry <= tick.ask - minDist;
   if(orderType=="SELL_LIMIT")return entry >= tick.bid + minDist;
   return false;
}

bool CancelPendingBySignalId(string orderId)
{
   bool found=false;
   for(int i=OrdersTotal()-1;i>=0;i--)
   {
      ulong ticket=OrderGetTicket(i);
      if(ticket==0) continue;
      long magic=OrderGetInteger(ORDER_MAGIC);
      if(magic!=SignalXMagic) continue;
      string comment=OrderGetString(ORDER_COMMENT);
      string symbol=OrderGetString(ORDER_SYMBOL);
      ENUM_ORDER_TYPE type=(ENUM_ORDER_TYPE)OrderGetInteger(ORDER_TYPE);
      bool pending=(type==ORDER_TYPE_BUY_LIMIT || type==ORDER_TYPE_SELL_LIMIT ||
                    type==ORDER_TYPE_BUY_STOP || type==ORDER_TYPE_SELL_STOP ||
                    type==ORDER_TYPE_BUY_STOP_LIMIT || type==ORDER_TYPE_SELL_STOP_LIMIT);
      if(!pending) continue;
      if(StringFind(comment,orderId)<0) continue;
      if(trade.OrderDelete(ticket))
      {
         found=true;
         Print("[AUTO TRADE] PENDING CANCELLED order_id=",orderId,
               " ticket=",ticket," symbol=",symbol);
      }
      else
      {
         Print("[AUTO TRADE] PENDING CANCEL FAILED order_id=",orderId,
               " ticket=",ticket," retcode=",trade.ResultRetcode(),
               " desc=",trade.ResultRetcodeDescription());
      }
   }
   return found;
}

void ProcessCancelCommands(string json)
{
   int scan=0;
   while((scan=StringFind(json,"\"cancel_orders\":[",scan))>=0)
   {
      int p=StringFind(json,"{",scan);
      if(p<0) break;
      int e=StringFind(json,"}",p);
      if(e<0) break;
      string c=StringSubstr(json,p,e-p+1);
      string id=JsonString(c,"order_id");
      if(id=="") id=JsonString(c,"signal_id");
      if(id!="")
      {
         CancelPendingBySignalId(id);
         string rr;
         string body="{\"order_id\":"+id+",\"status\":\"CANCELLED\",\"broker_message\":\"Pending setup cancelled by SignalX\"}";
         Http("POST","/api/v1/mt5/gateway/report",body,rr);
      }
      scan=e+1;
   }
}

double NormalizeVolume(string symbol,double requested)
{
   double minv=SymbolInfoDouble(symbol,SYMBOL_VOLUME_MIN);
   double maxv=SymbolInfoDouble(symbol,SYMBOL_VOLUME_MAX);
   double step=SymbolInfoDouble(symbol,SYMBOL_VOLUME_STEP);
   if(minv<=0 || maxv<=0 || step<=0) return 0.0;
   double v=requested>0 ? requested : DefaultLot;
   v=MathMax(minv,MathMin(maxv,v));
   v=MathFloor((v+1e-12)/step)*step;
   int digits=(int)MathMax(0,MathCeil(-MathLog10(step)));
   return NormalizeDouble(v,digits);
}

string ExecSymbol(string market)
{
   string wanted=market;
   if(wanted=="") wanted=XAUTradeSymbol;
   if(IsExactAllowedSymbol(wanted) && IsUsableSymbol(wanted)) return wanted;
   if(Canonical(wanted)=="XAU/USD") return FindBrokerSymbol("XAU/USD");
   return "";
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

string MarketsSessionJson()
{
   string canonicals[3]={"XAU/USD","EUR/USD","GBP/USD"};
   string out="{";
   bool first=true;
   for(int i=0;i<3;i++)
   {
      string broker=FindBrokerSymbol(canonicals[i]);
      if(broker=="") continue;
      if(!first) out+=",";
      first=false;
      out+="\""+JsonEscape(canonicals[i])+"\":{";
      out+="\"connected\":true";
      out+=SessionStateJson(broker);
      out+="}";
   }
   out+="}";
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
   body+=",\"symbols\":"+SymbolsJson();
   body+=",\"markets\":"+MarketsSessionJson()+"}";
   string response;
   return Http("POST","/api/v1/mt5/gateway/state",body,response);
}

bool ParseAndExecute(string json){
   ProcessCancelCommands(json);
   int p=StringFind(json,"\"orders\":[");
   if(p<0) return true;
   p=StringFind(json,"{",p);
   if(p<0) return false;
   int e=StringFind(json,"}",p);
   if(e<0) return false;
   string o=StringSubstr(json,p,e-p+1);
   string order_id=JsonString(o,"order_id");
   if(order_id=="") order_id=IntegerToString((long)JsonNumber(o,"order_id"));
   string symbol=JsonString(o,"execution_symbol");
   symbol=ExecSymbol(symbol);
   string direction=JsonString(o,"direction");
   string source=JsonString(o,"source");
   string order_type=JsonString(o,"order_type");
   if(order_type=="") order_type="MARKET";
   StringToUpper(order_type);
   double entry=JsonNumber(o,"entry");
   double volume=JsonNumber(o,"volume");
   double sl=JsonNumber(o,"stop_loss");
   double tp=JsonNumber(o,"take_profit");
    double tp1=JsonNumber(o,"tp1");
    double tp2=JsonNumber(o,"tp2");
    if(tp2<=0) tp2=tp;
    if(tp<=0) tp=tp2;
   if(order_id=="" || order_id=="0" || symbol=="" || (direction!="BUY" && direction!="SELL")) return false;
   if(IsBlockedSource(source)){
      string report="{\"order_id\":\""+JsonEscape(order_id)+"\",\"status\":\"REJECTED\",\"broker_message\":\"SOURCE_NOT_ALLOWED\"}";
      string rr; Http("POST","/api/v1/mt5/gateway/report",report,rr); return false;
   }
   if(order_type!="MARKET" && !IsPendingOrderType(order_type)) return false;
   if(!IsExactAllowedSymbol(symbol)){
      string report="{\"order_id\":\""+JsonEscape(order_id)+"\",\"status\":\"REJECTED\",\"broker_message\":\"Unsupported execution symbol\"}";
      string rr; Http("POST","/api/v1/mt5/gateway/report",report,rr); return false;
   }
   if(!GuardAllows(order_id)){
      string report="{\"order_id\":\""+JsonEscape(order_id)+"\",\"status\":\"REJECTED\",\"broker_message\":\"Duplicate cooldown\"}";
      string rr; Http("POST","/api/v1/mt5/gateway/report",report,rr); return false;
   }
   if(!IsUsable(symbol)){
      string report="{\"order_id\":\""+JsonEscape(order_id)+"\",\"status\":\"REJECTED\",\"broker_message\":\"Symbol unavailable: "+JsonEscape(symbol)+"\"}";
      string rr; Http("POST","/api/v1/mt5/gateway/report",report,rr); return false;
   }
   if(IsPendingOrderType(order_type))
   {
      if(entry<=0) {
         string report="{\"order_id\":"+order_id+",\"status\":\"REJECTED\",\"broker_message\":\"Missing pending entry\"}";
         string rr; Http("POST","/api/v1/mt5/gateway/report",report,rr); return false;
      }
      entry=NormalizePrice(symbol,entry);
      if(!PendingEntryValid(symbol,order_type,entry))
      {
         string report="{\"order_id\":"+order_id+",\"status\":\"REJECTED\",\"broker_message\":\"INVALID_PENDING_ENTRY\"}";
         string rr; Http("POST","/api/v1/mt5/gateway/report",report,rr); return false;
      }
   }
   double bid=SymbolInfoDouble(symbol,SYMBOL_BID), ask=SymbolInfoDouble(symbol,SYMBOL_ASK);
   double point=SymbolInfoDouble(symbol,SYMBOL_POINT);
   if(point<=0) point=_Point;
   double spread=(ask-bid)/point;
   if(spread>MaxSpreadPoints){
      string report="{\"order_id\":\""+JsonEscape(order_id)+"\",\"status\":\"REJECTED\",\"broker_message\":\"Spread guard\"}";
      string rr; Http("POST","/api/v1/mt5/gateway/report",report,rr); return false;
   }
   if(!ValidSignalLevels(symbol,direction,sl,tp)){
      string report="{\"order_id\":\""+JsonEscape(order_id)+"\",\"status\":\"REJECTED\",\"broker_message\":\"INVALID_LEVEL_GEOMETRY\"}";
      string rr; Http("POST","/api/v1/mt5/gateway/report",report,rr); return false;
   }
   if(volume<=0) volume=DefaultLot;
   double vmin=SymbolInfoDouble(symbol,SYMBOL_VOLUME_MIN), vmax=SymbolInfoDouble(symbol,SYMBOL_VOLUME_MAX), vstep=SymbolInfoDouble(symbol,SYMBOL_VOLUME_STEP);
   if(vmin>0 && volume<vmin) volume=vmin;
   if(vmax>0 && volume>vmax) volume=vmax;
   if(vstep>0) volume=MathFloor(volume/vstep)*vstep;
   if(volume<=0){
      string report="{\"order_id\":\""+JsonEscape(order_id)+"\",\"status\":\"REJECTED\",\"broker_message\":\"INVALID_VOLUME\"}";
      string rr; Http("POST","/api/v1/mt5/gateway/report",report,rr); return false;
   }
   if(MaxOpenPositionsPerSymbol>0 && CountSignalXPositions(symbol)>=MaxOpenPositionsPerSymbol){
      string report="{\"order_id\":\""+JsonEscape(order_id)+"\",\"status\":\"REJECTED\",\"broker_message\":\"MAX_OPEN_POSITIONS\"}";
      string rr; Http("POST","/api/v1/mt5/gateway/report",report,rr); return false;
   }
   if(!HasEnoughMargin(symbol,direction,volume)){
      string report="{\"order_id\":\""+JsonEscape(order_id)+"\",\"status\":\"REJECTED\",\"broker_message\":\"INSUFFICIENT_FREE_MARGIN\"}";
      string rr; Http("POST","/api/v1/mt5/gateway/report",report,rr); return false;
   }
   trade.SetExpertMagicNumber(SignalXMagic);
   trade.SetDeviationInPoints(MaxDeviationPoints);
   bool sent=false;
   string last="";
   int attempts=MathMax(1,MathMin(3,ExecutionRetries+1));
   datetime expiry=0;
   string expiryText=JsonString(o,"expires_at");
   if(expiryText!="")
   {
      // ISO timestamps are parsed server-side; MT5 receives a Unix timestamp when supplied.
      double expiryEpoch=JsonNumber(o,"expiry_epoch");
      if(expiryEpoch>0) expiry=(datetime)expiryEpoch;
   }
   if(expiry<=TimeCurrent()) expiry=TimeCurrent()+900;

   for(int attempt=0;attempt<attempts && !sent;attempt++){
      ResetLastError();
      sl=NormalizePrice(symbol,sl);
      tp=NormalizePrice(symbol,tp);
      tp2=tp;
      if(!ValidExecutionRR(symbol,direction,order_type,entry,sl,tp)){ last="RR_BELOW_1_OR_INVALID_GEOMETRY"; break; }
      if(IsPendingOrderType(order_type))
      {
         if(!PendingEntryValid(symbol,order_type,entry)){ last="INVALID_PENDING_ENTRY"; break; }
         if(!ValidSignalLevels(symbol,direction,sl,tp)){ last="INVALID_LEVEL_GEOMETRY"; break; }
         ENUM_ORDER_TYPE_TIME tt=(expiry>TimeCurrent() ? ORDER_TIME_SPECIFIED : ORDER_TIME_GTC);
         datetime ex=(tt==ORDER_TIME_SPECIFIED ? expiry : 0);
         if(order_type=="BUY_STOP") sent=trade.BuyStop(volume,entry,symbol,sl,tp2,tt,ex,"SignalX "+order_id);
         else if(order_type=="SELL_STOP") sent=trade.SellStop(volume,entry,symbol,sl,tp2,tt,ex,"SignalX "+order_id);
         else if(order_type=="BUY_LIMIT") sent=trade.BuyLimit(volume,entry,symbol,sl,tp2,tt,ex,"SignalX "+order_id);
         else if(order_type=="SELL_LIMIT") sent=trade.SellLimit(volume,entry,symbol,sl,tp2,tt,ex,"SignalX "+order_id);
      }
      else
      {
         if(!ValidSignalLevels(symbol,direction,sl,tp)){ last="INVALID_LEVEL_GEOMETRY"; break; }
         if(!HasEnoughMargin(symbol,direction,volume)){ last="INSUFFICIENT_FREE_MARGIN"; break; }
         if(direction=="BUY") sent=trade.Buy(volume,symbol,0,sl,tp2,"SignalX "+order_id);
         else sent=trade.Sell(volume,symbol,0,sl,tp2,"SignalX "+order_id);
      }
      uint rc=trade.ResultRetcode();
      sent=sent && (rc==TRADE_RETCODE_DONE || rc==TRADE_RETCODE_DONE_PARTIAL || rc==TRADE_RETCODE_PLACED);
      if(sent) SXStoreTPLevels(order_id,tp1,tp2);
      if(!sent){
         last=trade.ResultRetcodeDescription();
         if(!IsTransientRetcode(rc)) break;
         if(attempt+1<attempts) Sleep(300);
      }
   }
   ulong deal_ticket=trade.ResultDeal();
   ulong order_ticket=trade.ResultOrder();
   string status=!sent?"FAILED":(IsPendingOrderType(order_type)?"PENDING_PLACED":(deal_ticket>0?"FILLED":"SENT"));
   string report="{\"order_id\":"+order_id+",\"status\":\""+status+"\",\"broker_ticket\":\""+IntegerToString((long)(deal_ticket>0?deal_ticket:order_ticket));
   report+="\",\"broker_retcode\":\""+IntegerToString((int)trade.ResultRetcode())+"\",\"broker_message\":\""+JsonEscape(sent?"ORDER_SENT":last)+"\"}";
   if(sent) GlobalVariableSet(OrderGuardKey(order_id)+".done",(double)TimeCurrent());
   string rr; Http("POST","/api/v1/mt5/gateway/report",report,rr);
   if(sent) MarkOrderGuard(order_id);
   Print("[SIGNALX GATEWAY] ",status," order=",order_id," symbol=",symbol," direction=",direction," volume=",DoubleToString(volume,2));
   return sent;
}

void Poll(){
   if(!g_registered) return;
   // Poll even when the market is closed so SignalX can deliver cancellation
   // commands for already-placed pending BUY/SELL STOP/LIMIT orders.
   string response;
   if(Http("GET","/api/v1/mt5/gateway/poll","",response)) ParseAndExecute(response);
}

int OnInit(){
   EventSetTimer(1);
   if(!Register()) Print("[SIGNALX GATEWAY] Waiting for valid pairing code / WebRequest permission.");
   return INIT_SUCCEEDED;
}


// --- SignalX TP1/TP2 partial-close lifecycle ---
string SXTP1Key(string order_id) { return "SignalX.TP1."+IntegerToString((long)AccountInfoInteger(ACCOUNT_LOGIN))+"."+order_id; }
string SXTP2Key(string order_id) { return "SignalX.TP2."+IntegerToString((long)AccountInfoInteger(ACCOUNT_LOGIN))+"."+order_id; }
string SXTPDoneKey(ulong ticket) { return "SignalX.TP1DONE."+IntegerToString((long)AccountInfoInteger(ACCOUNT_LOGIN))+"."+IntegerToString((long)ticket); }

double SXNormalizeVolume(double v,string symbol)
{
   double vmin=SymbolInfoDouble(symbol,SYMBOL_VOLUME_MIN);
   double vmax=SymbolInfoDouble(symbol,SYMBOL_VOLUME_MAX);
   double step=SymbolInfoDouble(symbol,SYMBOL_VOLUME_STEP);
   if(step<=0) step=vmin;
   if(step<=0) return 0;
   v=MathMin(v,vmax);
   v=MathFloor(v/step+1e-9)*step;
   int digits=0; double x=step;
   while(digits<8 && MathAbs(x-MathRound(x))>1e-9){x*=10.0;digits++;}
   return NormalizeDouble(v,digits);
}

void SXStoreTPLevels(string order_id,double tp1,double tp2)
{
   if(order_id=="" || tp1<=0 || tp2<=0) return;
   GlobalVariableSet(SXTP1Key(order_id),tp1);
   GlobalVariableSet(SXTP2Key(order_id),tp2);
}

bool SXGetOrderIdFromComment(string comment,string &order_id)
{
   int p=StringFind(comment,"SignalX ");
   if(p<0) return false;
   int a=p+8;
   int e=StringFind(comment," ",a);
   if(e<0) order_id=StringSubstr(comment,a);
   else order_id=StringSubstr(comment,a,e-a);
   return order_id!="";
}

void SXHandleTP1TP2()
{
   if(!EnableTP1PartialClose) return;

   for(int i=PositionsTotal()-1;i>=0;--i)
   {
      ulong ticket=PositionGetTicket(i);
      if(ticket==0 || !PositionSelectByTicket(ticket)) continue;

      string symbol=PositionGetString(POSITION_SYMBOL);
      string comment=PositionGetString(POSITION_COMMENT);
      string order_id="";
      if(!SXGetOrderIdFromComment(comment,order_id)) continue;

      string k1=SXTP1Key(order_id), k2=SXTP2Key(order_id), kd=SXTP1DoneKey(ticket);
      if(!GlobalVariableCheck(k1) || !GlobalVariableCheck(k2) || GlobalVariableCheck(kd)) continue;

      double tp1=GlobalVariableGet(k1);
      double tp2=GlobalVariableGet(k2);
      if(tp1<=0 || tp2<=0) continue;

      long type=PositionGetInteger(POSITION_TYPE);
      double bid=SymbolInfoDouble(symbol,SYMBOL_BID);
      double ask=SymbolInfoDouble(symbol,SYMBOL_ASK);
      bool reached=(type==POSITION_TYPE_BUY ? bid>=tp1 : ask<=tp1);
      if(!reached) continue;

      double volume=PositionGetDouble(POSITION_VOLUME);
      double vmin=SymbolInfoDouble(symbol,SYMBOL_VOLUME_MIN);

      // SignalX rule:
      // > minimum lot: close 75% at TP1; keep 25% for TP2.
      // SL is moved to the original entry (break-even) after TP1.
      // A 0.01 minimum position cannot be split below broker minimum,
      // so it is handled as a single TP1-final position.
      bool is_min_lot=(volume <= vmin + 1e-9);
      double closeVol=0.0;

      if(!is_min_lot)
         closeVol=SXNormalizeVolume(volume*0.75,symbol);

      bool action_ok=false;

      if(is_min_lot || closeVol<=0.0 || (volume-closeVol)<vmin)
      {
         // Broker minimum lot cannot leave a valid 25% remainder.
         // TP1 is therefore the effective final target for this minimum lot.
         action_ok=true;
      }
      else
      {
         ResetLastError();
         action_ok=trade.PositionClosePartial(ticket,closeVol);
      }

      if(action_ok)
      {
         double entry=PositionGetDouble(POSITION_PRICE_OPEN);
         double be=NormalizePrice(symbol,entry);

         if(is_min_lot)
         {
            if(PositionSelectByTicket(ticket))
               trade.PositionModify(ticket,be,tp1);
         }
         else
         {
            // Remaining 25% continues to TP2; SL is now at break-even.
            if(PositionSelectByTicket(ticket))
               trade.PositionModify(ticket,be,tp2);
         }

         GlobalVariableSet(kd,1.0);
      }
   }
}



void OnDeinit(const int reason){ EventKillTimer(); }

void OnTimer(){
   SXHandleTP1TP2();

   datetime now=TimeCurrent();
   if(!g_registered && StringLen(PairingCode)>=6) Register();
   if(g_registered && (now-g_last_state)>=StateSeconds){ SendState(); g_last_state=now; }
   if(g_registered && (now-g_last_poll)>=PollSeconds){ Poll(); g_last_poll=now; }
}
