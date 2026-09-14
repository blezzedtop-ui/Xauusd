#property strict
#property version   "2.0"
#property description "SignalX MT5 bridge for XAUUSDm + EURUSDm. Attach ONE instance to each symbol chart."

#include <Trade/Trade.mqh>
CTrade trade;

input string ApiBase="https://signalx.asia";
input string BridgeToken="SignalX_MT5_2026_9Kx7P2mQ";
input int    PollSeconds=2;
input int    StateSeconds=5;
input double DefaultLot=0.01;
input int    DeviationPoints=50;

// FIXED broker symbols requested by user. No suffixless fallback is used.
const string XAU_SYMBOL="XAUUSDm";
const string EUR_SYMBOL="EURUSDm";

datetime g_last_state=0;

string Url(string path)
{
   return ApiBase+path;
}

string UpperCopy(string value)
{
   string out=value;
   StringToUpper(out);
   return out;
}

string JsonEscape(string value)
{
   string out=value;
   StringReplace(out,"\\","\\\\");
   StringReplace(out,"\"","\\\"");
   StringReplace(out,"\r","\\r");
   StringReplace(out,"\n","\\n");
   return out;
}

bool IsSupportedChart()
{
   return (_Symbol==XAU_SYMBOL || _Symbol==EUR_SYMBOL);
}

string CurrentMarket()
{
   if(_Symbol==XAU_SYMBOL) return "XAU/USD";
   if(_Symbol==EUR_SYMBOL) return "EUR/USD";
   return "";
}

string CurrentTradeSymbol()
{
   if(_Symbol==XAU_SYMBOL) return XAU_SYMBOL;
   if(_Symbol==EUR_SYMBOL) return EUR_SYMBOL;
   return "";
}

bool EnsureSymbol(string symbol)
{
   if(symbol=="") return false;
   if(!SymbolSelect(symbol,true))
   {
      Print("[MT5 BRIDGE] SymbolSelect failed: ",symbol," err=",GetLastError());
      return false;
   }
   MqlTick tick;
   if(!SymbolInfoTick(symbol,tick))
   {
      Print("[MT5 BRIDGE] SymbolInfoTick failed: ",symbol," err=",GetLastError());
      return false;
   }
   if(tick.bid<=0 || tick.ask<=0)
   {
      Print("[MT5 BRIDGE] No valid tick for ",symbol," bid=",tick.bid," ask=",tick.ask);
      return false;
   }
   return true;
}

string TFKey(ENUM_TIMEFRAMES tf)
{
   if(tf==PERIOD_M1)  return "1min";
   if(tf==PERIOD_M5)  return "5min";
   if(tf==PERIOD_M15) return "15min";
   if(tf==PERIOD_M30) return "30min";
   if(tf==PERIOD_H1)  return "1h";
   if(tf==PERIOD_H4)  return "4h";
   if(tf==PERIOD_D1)  return "1day";
   return EnumToString(tf);
}

string RatesJson(string symbol,ENUM_TIMEFRAMES tf,int count)
{
   MqlRates rates[];
   int copied=CopyRates(symbol,tf,0,count,rates);
   if(copied<=0) return "[]";

   string out="[";
   for(int i=0;i<copied;i++)
   {
      if(i>0) out+=",";
      out+=StringFormat(
         "{\"time\":%I64d,\"open\":%.10f,\"high\":%.10f,\"low\":%.10f,\"close\":%.10f,\"tick_volume\":%I64d}",
         (long)rates[i].time,
         rates[i].open,
         rates[i].high,
         rates[i].low,
         rates[i].close,
         (long)rates[i].tick_volume
      );
   }
   out+="]";
   return out;
}

int Http(string method,string url,string body,string &out)
{
   char data[];
   if(StringLen(body)>0)
      StringToCharArray(body,data,0,StringLen(body),CP_UTF8);

   char result[];
   string headers="Content-Type: application/json\r\n";
   string result_headers="";

   ResetLastError();
   int code=WebRequest(method,url,headers,5000,data,result,result_headers);
   int err=GetLastError();
   out=CharArrayToString(result,0,-1,CP_UTF8);

   Print("[MT5 BRIDGE] ",method," ",url," -> HTTP=",code," LastError=",err," Response=",out);
   return code;
}

void AppendCurrentMarketState(string &body)
{
   string symbol=CurrentTradeSymbol();
   body+="\""+JsonEscape(CurrentMarket())+"\":{";
   body+="\"connected\":true";
   body+=",\"account\":\""+IntegerToString((long)AccountInfoInteger(ACCOUNT_LOGIN))+"\"";
   body+=",\"server\":\""+JsonEscape(AccountInfoString(ACCOUNT_SERVER))+"\"";
   body+=",\"balance\":"+DoubleToString(AccountInfoDouble(ACCOUNT_BALANCE),2);
   body+=",\"equity\":"+DoubleToString(AccountInfoDouble(ACCOUNT_EQUITY),2);
   body+=",\"free_margin\":"+DoubleToString(AccountInfoDouble(ACCOUNT_MARGIN_FREE),2);
   body+=",\"margin\":"+DoubleToString(AccountInfoDouble(ACCOUNT_MARGIN),2);
   body+=",\"positions\":"+IntegerToString(PositionsTotal());
   body+=",\"symbol\":\""+JsonEscape(symbol)+"\"";
   body+=",\"candles\":{";

   ENUM_TIMEFRAMES tfs[6]={PERIOD_M5,PERIOD_M15,PERIOD_M30,PERIOD_H1,PERIOD_H4,PERIOD_D1};
   for(int i=0;i<6;i++)
   {
      if(i>0) body+=",";
      body+="\""+TFKey(tfs[i])+"\":"+RatesJson(symbol,tfs[i],120);
   }
   body+="}}";
}

void ReportState()
{
   string market=CurrentMarket();
   if(market=="") return;

   string body="{";
   body+="\"connected\":true";
   body+=",\"symbol\":\""+JsonEscape(market)+"\"";
   body+=",\"login\":\""+IntegerToString((long)AccountInfoInteger(ACCOUNT_LOGIN))+"\"";
   body+=",\"server\":\""+JsonEscape(AccountInfoString(ACCOUNT_SERVER))+"\"";
   body+=",\"balance\":"+DoubleToString(AccountInfoDouble(ACCOUNT_BALANCE),2);
   body+=",\"equity\":"+DoubleToString(AccountInfoDouble(ACCOUNT_EQUITY),2);
   body+=",\"free_margin\":"+DoubleToString(AccountInfoDouble(ACCOUNT_MARGIN_FREE),2);
   body+=",\"margin\":"+DoubleToString(AccountInfoDouble(ACCOUNT_MARGIN),2);
   body+=",\"positions\":"+IntegerToString(PositionsTotal());
   body+=",\"markets\":{";
   AppendCurrentMarketState(body);
   body+="}}";

   string out;
   Http("POST",Url("/api/v1/mt5/state?token="+BridgeToken),body,out);
}

string ExtractString(string json,string key,int from_pos)
{
   string needle="\""+key+"\":\"";
   int p=StringFind(json,needle,from_pos);
   if(p<0) return "";
   int s=p+StringLen(needle);
   int e=StringFind(json,"\"",s);
   if(e<0) return "";
   return StringSubstr(json,s,e-s);
}

double ExtractNumber(string json,string key,int from_pos)
{
   string needle="\""+key+"\":";
   int p=StringFind(json,needle,from_pos);
   if(p<0) return 0.0;
   int s=p+StringLen(needle);
   while(s<StringLen(json))
   {
      ushort c=StringGetCharacter(json,s);
      if(c==' ' || c=='\t') s++;
      else break;
   }
   int e=s;
   while(e<StringLen(json))
   {
      ushort c=StringGetCharacter(json,e);
      if((c>='0' && c<='9') || c=='-' || c=='+' || c=='.' || c=='e' || c=='E') e++;
      else break;
   }
   if(e<=s) return 0.0;
   return StringToDouble(StringSubstr(json,s,e-s));
}

double ExtractFirstTP(string json,int from_pos)
{
   int p=StringFind(json,"\"tp\":[",from_pos);
   if(p<0) return 0.0;
   int s=p+StringLen("\"tp\":[");
   int e=s;
   while(e<StringLen(json))
   {
      ushort c=StringGetCharacter(json,e);
      if((c>='0' && c<='9') || c=='-' || c=='+' || c=='.' || c=='e' || c=='E') e++;
      else break;
   }
   if(e<=s) return 0.0;
   return StringToDouble(StringSubstr(json,s,e-s));
}

void SendReport(string order_id,string action,string status,string symbol,string message)
{
   string rb=StringFormat(
      "{\"action\":\"%s\",\"ticket\":\"%s\",\"symbol\":\"%s\",\"status\":\"%s\",\"message\":\"%s\"}",
      JsonEscape(action),JsonEscape(order_id),JsonEscape(symbol),JsonEscape(status),JsonEscape(message)
   );
   string out;
   Http("POST",Url("/api/v1/mt5/report?token="+BridgeToken),rb,out);
}

bool ValidStops(string symbol,string dir,double sl,double tp)
{
   MqlTick tick;
   if(!SymbolInfoTick(symbol,tick)) return false;

   int digits=(int)SymbolInfoInteger(symbol,SYMBOL_DIGITS);
   double point=SymbolInfoDouble(symbol,SYMBOL_POINT);
   long stops_level=SymbolInfoInteger(symbol,SYMBOL_TRADE_STOPS_LEVEL);
   double min_distance=(double)stops_level*point;

   sl=NormalizeDouble(sl,digits);
   tp=NormalizeDouble(tp,digits);

   if(dir=="BUY")
      return (sl>0 && tp>0 && sl<tick.bid-min_distance && tp>tick.ask+min_distance);
   if(dir=="SELL")
      return (sl>0 && tp>0 && sl>tick.ask+min_distance && tp<tick.bid-min_distance);
   return false;
}

void ExecuteOrder(string order_id,string dir,string requested_symbol,string order_market,
                  string source,double volume,double entry,double sl,double tp)
{
   string expectedMarket=CurrentMarket();
   string expectedSymbol=CurrentTradeSymbol();

   string req=UpperCopy(requested_symbol);
   string mkt=UpperCopy(order_market);

   bool symbolOk=((expectedMarket=="XAU/USD" && StringFind(req,"XAUUSD")>=0) ||
                  (expectedMarket=="EUR/USD" && StringFind(req,"EURUSD")>=0));
   bool marketOk=((expectedMarket=="XAU/USD" && StringFind(mkt,"XAU")>=0) ||
                  (expectedMarket=="EUR/USD" && StringFind(mkt,"EUR")>=0));

   if(!symbolOk || !marketOk)
   {
      SendReport(order_id,dir,"ORDER_FAILED",expectedSymbol,"BLOCKED cross-symbol order");
      Print("[MT5 BRIDGE] BLOCKED order=",order_id," requested_symbol=",requested_symbol," market=",order_market," expected=",expectedMarket);
      return;
   }

   if(!EnsureSymbol(expectedSymbol))
   {
      SendReport(order_id,dir,"ORDER_FAILED",expectedSymbol,"Trading symbol unavailable");
      return;
   }

   if(volume<=0) volume=DefaultLot;
   if(!ValidStops(expectedSymbol,dir,sl,tp))
   {
      SendReport(order_id,dir,"ORDER_FAILED",expectedSymbol,
                 "Invalid live SL/TP for current price");
      Print("[MT5 BRIDGE] INVALID STOPS order=",order_id," market=",expectedMarket,
            " entry=",DoubleToString(entry,8)," sl=",DoubleToString(sl,8)," tp=",DoubleToString(tp,8));
      return;
   }

   trade.SetAsyncMode(false);
   trade.SetDeviationInPoints(DeviationPoints);
   trade.SetTypeFillingBySymbol(expectedSymbol);

   string comment="SignalX "+(source==""?"AUTO":source);
   bool ok=false;
   if(dir=="BUY")  ok=trade.Buy(volume,expectedSymbol,0.0,sl,tp,comment);
   if(dir=="SELL") ok=trade.Sell(volume,expectedSymbol,0.0,sl,tp,comment);

   uint retcode=trade.ResultRetcode();
   string desc=trade.ResultRetcodeDescription();
   ulong deal=trade.ResultDeal();

   Print("[MT5 BRIDGE] EXECUTION market=",expectedMarket," symbol=",expectedSymbol,
         " dir=",dir," volume=",DoubleToString(volume,2),
         " entry_signal=",DoubleToString(entry,8),
         " sl=",DoubleToString(sl,8)," tp=",DoubleToString(tp,8),
         " ok=",ok," retcode=",retcode," deal=",deal," desc=",desc);

   if(ok && (retcode==TRADE_RETCODE_DONE || retcode==TRADE_RETCODE_DONE_PARTIAL || deal>0))
      SendReport(order_id,dir,"ORDER_SENT",expectedSymbol,desc);
   else
      SendReport(order_id,dir,"ORDER_FAILED",expectedSymbol,desc);
}

bool PollCurrentMarket()
{
   string market=CurrentMarket();
   string encoded=market;
   StringReplace(encoded,"/","%2F");

   string out;
   int code=Http("GET",Url("/api/v1/mt5/poll?token="+BridgeToken+"&market="+encoded),"",out);
   if(code!=200)
   {
      Print("[MT5 BRIDGE] POLL FAILED market=",market," HTTP=",code);
      return false;
   }

   if(StringFind(out,"\"orders\":[]")>=0)
   {
      Print("[MT5 BRIDGE] POLL OK market=",market," - no queued orders");
      return true;
   }

   int pos=0;
   while((pos=StringFind(out,"\"id\":\"",pos))>=0)
   {
      string order_id=ExtractString(out,"id",pos);
      string dir=UpperCopy(ExtractString(out,"direction",pos));
      string requested_symbol=ExtractString(out,"symbol",pos);
      string order_market=ExtractString(out,"market",pos);
      string source=ExtractString(out,"source",pos);
      double entry=ExtractNumber(out,"entry",pos);
      double sl=ExtractNumber(out,"sl",pos);
      double tp=ExtractFirstTP(out,pos);
      double volume=ExtractNumber(out,"volume",pos);
      ExecuteOrder(order_id,dir,requested_symbol,order_market,source,volume,entry,sl,tp);
      pos+=MathMax(1,StringLen(order_id));
   }
   return true;
}

int OnInit()
{
   if(!IsSupportedChart())
   {
      Print("[MT5 BRIDGE] ATTACH ONLY TO XAUUSDm OR EURUSDm. Current chart=",_Symbol);
      return(INIT_FAILED);
   }

   if(!EnsureSymbol(CurrentTradeSymbol()))
      return(INIT_FAILED);

   trade.SetAsyncMode(false);
   trade.SetDeviationInPoints(DeviationPoints);
   trade.SetTypeFillingBySymbol(CurrentTradeSymbol());

   EventSetTimer(MathMax(1,PollSeconds));
   Print("[MT5 BRIDGE] STARTED market=",CurrentMarket(),
         " chart=",_Symbol," ApiBase=",ApiBase," PollSeconds=",PollSeconds,
         " Lot=",DoubleToString(DefaultLot,2));
   Print("[MT5 BRIDGE] WebRequest allow URL: ",ApiBase);
   return(INIT_SUCCEEDED);
}

void OnDeinit(const int reason)
{
   EventKillTimer();
   Print("[MT5 BRIDGE] STOPPED market=",CurrentMarket()," reason=",reason);
}

void OnTimer()
{
   if(g_last_state==0 || (TimeCurrent()-g_last_state)>=StateSeconds)
   {
      ReportState();
      g_last_state=TimeCurrent();
   }
   PollCurrentMarket();
}
