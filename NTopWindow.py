import matplotlib
import pandas as pd
import sys
sys.path.extend(['/home/Spare/CC/datascripts'])
import getdata
import mungeData
from multiprocessing import Process, Queue
import StoreDF
import datetime

hrs = [1, 6, 12, 24]
periods = [2, 4, 8, 16, 24]
periodend = 0
column = 'price_btc'

#This function TrialHrsSym checks to see
def TrialHrsSym(hrs,periods,periodend,column):
    mean = []
    std = []
    chg = []
    for window in hrs:
        df = mungeData.avgrnkba(column, window, periods[1], periodend)
        mean.append(pd.DataFrame(df['mean']))
        std.append(pd.DataFrame(df['std']))
        chg.append(pd.DataFrame(df['%chg']))
    mean = pd.concat(mean, axis=1)
    std = pd.concat(std, axis=1)
    chg = pd.concat(chg, axis=1)
    mean.columns = hrs
    std.columns = hrs
    chg.columns= hrs
    p4t40 = []
    for hr in hrs:
        p4t40.append(pd.DataFrame(mean.sort_values(by=hr).index[:40]))
    p4top40 = pd.concat(p4t40, axis=1)
    p4top40.columns = hrs
    return

def topNwindow(top200, winCol,rankCol,N):
    # winCol = data column over which the windowing occurs, rankCol = data summary column over which the ranking occurs.
    # mungeData.avgrnkba(column, win, per, perend) - perend defines the end of the period
    df1 = mungeData.avgrnkba(winCol, 6, 7, 0)
    df2 = mungeData.avgrnkba(winCol, 3, 3, 0)
    topn = mungeData.topNcompare(df1,df2,rankCol,N)
    return topn

per = 2
perend = 0
column = 'price_btc'
tablelist = StoreDF.get_last_update('cmcdataset')

def get_data_range(tablelist,winper,perend,column):
    [window, period, periodend] = mungeData.conv_win_2_block(0, winper, perend)
    lastupdate = datetime.datetime.strptime(max(tablelist.last_updated),"%Y-%m-%d %H:%M")
    if periodend == 0:
        enddate = lastupdate
    else:
        enddate = lastupdate - datetime.timedelta(minutes = 5*periodend)
    startdate = enddate - datetime.timedelta(minutes = 5*period)
    store = StoreDF.select_HDFstore('cmcdataset')
    syms = tablelist.index
    mktcap = []
    othercol = []
    for sym in syms:
        symdata = store.get(sym)
        symdata = symdata.loc[~symdata.index.duplicated(keep='first')]
        lastsymupdate = datetime.datetime.strptime(tablelist.loc[sym][0],"%Y-%m-%d %H:%M")
        if lastsymupdate > startdate:
            if lastsymupdate < enddate:
                end = lastsymupdate
            else:
                end = enddate
            #First 5min entry was at 2018-03-17 22:51
            firstentry = symdata.iloc[0].name.replace(tzinfo=None)
            if firstentry > startdate:
                start = firstentry
            else:
                start = startdate
            mktcap.append(symdata.mkt_cap.loc[start:end].rename(sym))
            coldata = symdata[[column]].loc[start:end]
            coldata.set_axis([sym], axis=1, inplace=True)
            othercol.append(coldata)
    mcp = pd.concat(mktcap,axis=1)
    ocol = pd.concat(othercol,axis=1)
    return mcp,ocol

def rollingtopN(window, perend, winX, hrX, winY, hrY, column, N):
    #extra day for the 6pm daily re-shuffle
    window = window + 1
    ## window = n days over which the analysis takes place,
    ## winX = n days, larger of X and Y, duration over which the first ranking window occurs
    ## winY = n days, smaller of X and Y, duration over which the second ranking window occurs
    ## hrX = n hours, hourly interval over which the rolling average window for winX occurs
    ## hrY = n hours, hourly interval over which the rolling average window for winY occurs
    ## column = dataset column used for the analysis, generally 'price_btc' or 'price_usd'
    ## N = topN

    # Re-arrange winX and winY so that winX is larger than winY
    '''if winX < winY:
        temp = winX
        winX = winY
        winY = temp
        temp = hrX
        hrX = hrY
        hyY = temp'''
    # Gets existing data for the window,
    # For each day:
    # Identifies the top 200 for the day
    # Determines average return rank (ARR) for the top 200 over the previous X days,
    # Compares it to the ARR for the top 200 over the last Y days,
    # See's which currencies are shared over both sets,
    # Removes the top 3 (usually bogus data or stupid coins) and records the symbols and dates.
    # Relies on another function to give prices for the 'buys' and 'sells'

    tablelist = StoreDF.get_tlisth5('cmcdataset')
    [mcp, pbtc] = get_data_range(tablelist, window, perend, column)
    daystop200 = []
    for i in mcp.index:
        dtop200 = mcp.loc[i].dropna().sort_values().iloc[-199:].index
        daystop200.append(dtop200)
    daystop200df = pd.DataFrame(daystop200,index=mcp.index)
    # Every day at 6pm perform the rolling window calculations on the price dataframe and spit out the top40
    firstentry = daystop200df.index[0]
    # Get firstentry after the longest rolling window
    fearw = firstentry + datetime.timedelta(days = winX)
    # find the first 6pm:
    t1 = datetime.time(hour=18, minute=5)
    t2 = datetime.time(hour=17, minute=58)
    df = daystop200df.loc[daystop200df.index.time < t1]
    df2 = df.loc[df.index.time > t2]
    times = df2.loc[df2.index > fearw].index
    # perform calcs on winX and winY
    winXmrank = []
    winXsrank = []
    winYmrank = []
    winYsrank = []
    for time in times:
        [mrankdfX, srankdfX] = rankattime(time, winX, hrX, pbtc)
        [mrankdfY, srankdfY] = rankattime(time, winY, hrY, pbtc)
        winXmrank.append(mrankdfX)
        winXsrank.append(srankdfX)
        winYmrank.append(mrankdfY)
        winYsrank.append(srankdfY)
    winXmrankdf = pd.concat(winXmrank,axis=1)
    winXmrankdf.columns = times.strftime("%Y-%m-%d %H:%M")
    winXsrankdf = pd.concat(winXsrank, axis=1)
    winXsrankdf.columns = times.strftime("%Y-%m-%d %H:%M")
    winYmrankdf = pd.concat(winYmrank, axis=1)
    winYmrankdf.columns = times.strftime("%Y-%m-%d %H:%M")
    winYsrankdf = pd.concat(winYsrank, axis=1)
    winYsrankdf.columns = times.strftime("%Y-%m-%d %H:%M")
    cols = winXmrankdf.columns
    topNcom = []
    for col in cols:
        topNboth = topNcompind(winXmrankdf[col], winYmrankdf[col], N)
        topNcom.append(topNboth)
    topN = pd.concat(topNcom,axis=1)
    topN.columns = times.strftime("%Y-%m-%d %H:%M")
    cols = topN.columns
    topNshare = []
    for i in range(0,len(cols)-1):
        topNboth = topNcompsym(topN[cols[i+1]], topN[cols[i]]).reset_index(drop=True)
        topNshare.append(topNboth)
    topNcarried = pd.concat(topNshare,axis=1)
    return topNshare, topNcarried

def topNbuysell(topN,pbtc):
    #goes through the topN, determines which ones are new to the list (to be bought) and which ones have been removed (to be sold)
    times = topN.columns
    symsprices = []
    buytx = []
    selltx = pd.DataFrame()
    wallet = pd.DataFrame()
    for i in range(0,len(times)):
        walletsyms = wallet.index
        thissyms = topN[times[i]].dropna()
        buysyms = thissyms[~thissyms.isin(walletsyms)]
        sellsyms = walletsyms[~walletsyms.isin(thissyms)]
        buyprices = pbtc[buysyms].loc[times[i]]
        sellprices = pbtc[sellsyms].loc[times[i]]
        buydf = pd.DataFrame(buyprices)
        buytx.append(buydf)
        buydf.columns = ['buy_price']
        buydf['buy_time'] = times[i]
        wallet = wallet.append(buydf)
        selldf = pd.DataFrame(sellprices)
        selldf.columns = ['sell_price']
        selldf['sell_time'] = times[i]
        prevbuyprices = wallet[['buy_price','buy_time']].loc[sellsyms]
        selldf = selldf.join(prevbuyprices)
        selldf['profit%'] = (selldf['sell_price'] - selldf['buy_price']).divide(selldf['buy_price'])
        selltx = selltx.append(selldf)
        wallet = wallet.drop(sellsyms)
        currentprices = pbtc[wallet.index].loc[times[i]]
        wallet['current_price'] = currentprices
        wallet['profit%'] = (wallet['current_price'] - wallet['buy_price']).divide(wallet['buy_price'])
    return buytx, wallet, selltx






    symsbtc = pd.concat(symsprices,axis=1)




def topNcompind(dfX,dfY,N):
    if N != 0:
        df1 = dfX.sort_values(ascending=False).dropna()
        df2 = dfY.sort_values(ascending=False).dropna()
        df1 = df1.iloc[-N:]
        df2 = df2.iloc[-N:]
    topNboth1 = df1[df1.index.isin(df2.index)]
    topNboth2 = df2[df2.index.isin(df1.index)]
    topNboth = pd.DataFrame(topNboth1[topNboth1.index.isin(topNboth2.index)].index.tolist())
    return topNboth

def topNcompsym(df1,df2):
    topNboth1 = df1[df1.isin(df2)]
    topNboth2 = df2[df2.isin(df1)]
    topNboth = pd.DataFrame(topNboth1[topNboth1.isin(topNboth2)])
    return topNboth

def rankattime(endtime, winX, hrX, pbtc):
    starttime = endtime - datetime.timedelta(days=winX)
    windata = pbtc[starttime:endtime]
    windata = windata[daystop200df.loc[endtime].dropna().values]
    [mrankdf, srankdf] = rolling_avg(windata, hrX)
    return mrankdf, srankdf

def rolling_avg(pbtc,hrX):
    # perform the rolling window calculations on the price dataframe
    pctchange = pbtc.pct_change()
    dflogreturn = np.log(1 + pctchange)
    dfdiffwinsum = dflogreturn.rolling(hrX*12).sum()
    rankdf = dfdiffwinsum.rank(1, ascending=False)
    mrankdf = rankdf.mean().rename('mean')
    srankdf = rankdf.std().rename('std')
    return mrankdf, srankdf

window = 28
perend = 0
winX = 15
hrX = 6
winY = 5
hrY = 3
N = 40
per = 5
perend = 0
column = 'price_btc'