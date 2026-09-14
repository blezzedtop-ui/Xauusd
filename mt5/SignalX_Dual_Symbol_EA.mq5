#property strict
#property version   "1.4"
#property description "SignalX dual-symbol XAUUSD + EURUSD MT5 bridge"

#include <Trade/Trade.mqh>
CTrade trade;

input string ApiBase="https://signalx.asia";
input string BridgeToken="SignalX_MT5_2026_9Kx7P2mQ";
input int    PollSeconds=2;
input int    StateSeconds=5;
input double DefaultLot=0.01;
input string TradeSymbol="";
input string XAUTradeSymbol="XAUUSDm";
input string XAUTradeSymbolNoSuffix="XAUUSD";
input string EURTradeSymbol="EURUSDm";
input string EURTradeSymbolNoSuffix="EURUSD";

string Url(string path){ return ApiBase+path; }
datetime g_last_state=0;

string JsonEscape(string s)
{
   StringReplace(s,"\\","\\\\");
   StringReplace(s,"\"","\\\"");
   return s;
}

void UpperInPlace(string &s)
{
   StringToUpper(s);
}

bool IsUsableSymbol(string symbol)
{
   if(StringLen(symbol)==0) return false;
   if(SymbolInfoDouble(symbol,SYMBOL_BID)>0) return true;
   if(!SymbolSelect(symbol,true)) return false;
   return (SymbolInfoDouble(symbol,SYMBOL_BID)>0);
}

string FindAvailableVariant(string preferred,string noSuffix,string base)
{
   if(IsUsableSymbol(preferred)) return preferred;
   if(IsUsableSymbol(noSuffix)) return noSuffix;

   string needle=base;
   UpperInPlace(needle);
   int total=SymbolsTotal(false);
   for(int i=0;i<total;i++)
   {
      string name=SymbolName(i,false);
      string up=name;
      UpperInPlace(up);
      if(StringFind(up,needle)>=0 && IsUsableSymbol(name))
         return name;
   }
   return "";
}

string ExecSymbol()
{
   if(StringLen(TradeSymbol)>0 && IsUsableSymbol(TradeSymbol)) return TradeSymbol;
   if(IsUsableSymbol(_Symbol)) return _Symbol;
   return "";
}

string XAUStateSymbol()
{
   return FindAvailableVariant(XAUTradeSymbol,XAUTradeSymbolNoSuffix,"XAUUSD");
}

string EURStateSymbol()
{
   return FindAvailableVariant(EURTradeSymbol,EURTradeSymbolNoSuffix,"EURUSD");
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
   ArraySetAsSeries(rates,false);
   int copied=CopyRates(symbol,tf,0,count,rates);
   if(copied<=0) return "[]";

   string out="[";
   bool first=true;
   int start=copied-count;
   if(start<0) start=0;
   for(int i=start;i<copied;i++)
   {
      if(!first) out+=",";
      first=false;
      out += StringFormat(
         "{\"time\":%I64d,\"open\":%.10f,\"high\":%.10f,\"low\":%.10f,\"close\":%.10f}",
         (long)rates[i].time,
         rates[i].open,
         rates[i].high,
         rates[i].low,
         rates[i].close
      );
   }
   out+="]";
   return out;
}

int Http(string method,string url,string body,string &out)
{
   char data[];
   int data_size=0;
   if(StringLen(body)>0)
      data_size=StringToCharArray(body,data,0,StringLen(body),CP_UTF8);

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

void AppendMarketState(string &body,string symbol,bool &firstMarket)
{
   if(!IsUsableSymbol(symbol)) return;
   if(!firstMarket) body+=",";
   firstMarket=false;

   ENUM_TIMEFRAMES tfs[6]={PERIOD_M5,PERIOD_M15,PERIOD_M30,PERIOD_H1,PERIOD_H4,PERIOD_D1};

   body += "\""+JsonEscape(symbol)+"\":{";
   body += "\"connected\":true";
   body += ",\"account\":\""+IntegerToString((long)AccountInfoInteger(ACCOUNT_LOGIN))+"\"";
   body += ",\"server\":\""+JsonEscape(AccountInfoString(ACCOUNT_SERVER))+"\"";
   body += ",\"balance\":"+DoubleToString(AccountInfoDouble(ACCOUNT_BALANCE),2);
   body += ",\"equity\":"+DoubleToString(AccountInfoDouble(ACCOUNT_EQUITY),2);
   body += ",\"free_margin\":"+DoubleToString(AccountInfoDouble(ACCOUNT_MARGIN_FREE),2);
   body += ",\"margin\":"+DoubleToString(AccountInfoDouble(ACCOUNT_MARGIN),2);
   body += ",\"positions\":"+IntegerToString(PositionsTotal());
   body += ",\"candles\":{";

   for(int i=0;i<6;i++)
   {
      if(i>0) body+=",";
      string key=TFKey(tfs[i]);
      body += "\""+key+"\":"+RatesJson(symbol,tfs[i],120);
   }
   body += "}}";
}

void ReportState()
{
   string xau=XAUStateSymbol();
   string eur=EURStateSymbol();

   string body="{";
   body += "\"connected\":true";
   body += ",\"symbol\":\"DUAL\"";
   body += ",\"login\":\""+IntegerToString((long)AccountInfoInteger(ACCOUNT_LOGIN))+"\"";
   body += ",\"server\":\""+JsonEscape(AccountInfoString(ACCOUNT_SERVER))+"\"";
   body += ",\"balance\":"+DoubleToString(AccountInfoDouble(ACCOUNT_BALANCE),2);
   body += ",\"equity\":"+DoubleToString(AccountInfoDouble(ACCOUNT_EQUITY),2);
   body += ",\"free_margin\":"+DoubleToString(AccountInfoDouble(ACCOUNT_MARGIN_FREE),2);
   body += ",\"margin\":"+DoubleToString(AccountInfoDouble(ACCOUNT_MARGIN),2);
   body += ",\"positions\":"+IntegerToString(PositionsTotal());
   body += ",\"candles\":{}";
   body += ",\"markets\":{";

   bool firstMarket=true;
   AppendMarketState(body,xau,firstMarket);
   AppendMarketState(body,eur,firstMarket);
   body += "}}";

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
   int e=s;
   while(e<StringLen(json))
   {
      ushort c=StringGetCharacter(json,e);
      if((c>='0' && c<='9') || c=='-' || c=='+' || c=='.' || c=='e' || c=='E') e++;
      else break;
   }
   return StringToDouble(StringSubstr(json,s,e-s));
}

double ExtractFirstTP(string json,int from_pos)
{
   string needle="\"tp\":[";
   int p=StringFind(json,needle,from_pos);
   if(p<0) return 0.0;
   int s=p+StringLen(needle);
   int e=s;
   while(e<StringLen(json))
   {
      ushort c=StringGetCharacter(json,e);
      if((c>='0' && c<='9') || c=='-' || c=='+' || c=='.' || c=='e' || c=='E') e++;
      else break;
   }
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

int OnInit()
{
   Print("[MT5 BRIDGE] STARTED chart=",_Symbol," ApiBase=",ApiBase," PollSeconds=",PollSeconds," Lot=",DoubleToString(DefaultLot,2));
   Print("[MT5 BRIDGE] WebRequest allow URL: ",ApiBase);
   EventSetTimer(MathMax(1,PollSeconds));
   return(INIT_SUCCEEDED);
}

void OnDeinit(const int reason)
{
   EventKillTimer();
   Print("[MT5 BRIDGE] STOPPED reason=",reason);
}

bool PollMarket(string requestedMarket,string expectedSymbol)
{
   string out;
   string encoded=requestedMarket;
   StringReplace(encoded,"/","%2F");
   int code=Http("GET",Url("/api/v1/mt5/poll?token="+BridgeToken+"&market="+encoded),"",out);
   if(code!=200)
   {
      Print("[MT5 BRIDGE] POLL FAILED market=",requestedMarket," HTTP=",code);
      return false;
   }

   if(StringFind(out,"\"orders\":[]")>=0)
      return true;

   int pos=0;
   while((pos=StringFind(out,"\"id\":\"",pos))>=0)
   {
      string order_id=ExtractString(out,"id",pos);
      string dir=ExtractString(out,"direction",pos);
      string requested_symbol=ExtractString(out,"symbol",pos);
      string order_market=ExtractString(out,"market",pos);
      string source=ExtractString(out,"source",pos);
      double entry=ExtractNumber(out,"entry",pos);
      double sl=ExtractNumber(out,"sl",pos);
      double tp=ExtractFirstTP(out,pos);
      double vol=ExtractNumber(out,"volume",pos);
      if(vol<=0) vol=DefaultLot;

      string req=requested_symbol;
      string mkt=order_market;
      string expected=expectedSymbol;
      UpperInPlace(req);
      UpperInPlace(mkt);
      UpperInPlace(expected);

      bool isEUR=(StringFind(requestedMarket,"EUR")>=0);
      bool marketMatches=isEUR ? (StringFind(mkt,"EUR")>=0) : (StringFind(mkt,"XAU")>=0);
      bool symbolMatches=isEUR ? (StringFind(req,"EURUSD")>=0) : (StringFind(req,"XAUUSD")>=0);
      if(!marketMatches || !symbolMatches)
      {
         SendReport(order_id,dir,"ORDER_FAILED",expectedSymbol,"BLOCKED: cross-symbol order rejected by EA");
         pos+=MathMax(1,StringLen(order_id));
         continue;
      }

      string execSymbol=isEUR
         ? FindAvailableVariant(EURTradeSymbol,EURTradeSymbolNoSuffix,"EURUSD")
         : FindAvailableVariant(XAUTradeSymbol,XAUTradeSymbolNoSuffix,"XAUUSD");

      if(StringLen(execSymbol)==0)
      {
         SendReport(order_id,dir,"ORDER_FAILED",expectedSymbol,"Symbol not available");
         pos+=MathMax(1,StringLen(order_id));
         continue;
      }

      trade.SetAsyncMode(false);
      string comment="SignalX "+(source==""?"AUTO":source);
      bool ok=false;
      if(dir=="BUY")  ok=trade.Buy(vol,execSymbol,0,sl,tp,comment);
      if(dir=="SELL") ok=trade.Sell(vol,execSymbol,0,sl,tp,comment);

      string desc=trade.ResultRetcodeDescription();
      if(ok) SendReport(order_id,dir,"ORDER_SENT",execSymbol,desc);
      else   SendReport(order_id,dir,"ORDER_FAILED",execSymbol,desc);

      pos+=MathMax(1,StringLen(order_id));
   }
   return true;
}

void OnTimer()
{
   if(g_last_state==0 || (TimeCurrent()-g_last_state)>=StateSeconds)
   {
      ReportState();
      g_last_state=TimeCurrent();
   }

   string xau=XAUStateSymbol();
   string eur=EURStateSymbol();
   PollMarket("XAU/USD",xau);
   PollMarket("EUR/USD",eur);
}
