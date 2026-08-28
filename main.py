import os
import requests
import traceback
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from supabase import create_client, Client

app = FastAPI()

# 1. 系統變數 (不再需要綁定個人玩家標籤了！)
SUPABASE_URL = os.environ.get("SUPABASE_URL", "").strip()
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "").strip()
BRAWL_API_TOKEN = os.environ.get("BRAWL_API_TOKEN", "").strip()

try:
    supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
except Exception as e:
    supabase = None

# 2. 爬蟲引擎：接收任意玩家標籤並抓取資料
def fetch_and_save_data(target_tag: str):
    if not supabase or not BRAWL_API_TOKEN:
        return False

    # 確保標籤格式正確 (自動補上 # 並轉大寫)
    target_tag = target_tag.strip().upper()
    if not target_tag.startswith("#"):
        target_tag = "#" + target_tag
        
    tag_formatted = target_tag.replace("#", "%23")
    url = f"https://bsproxy.royaleapi.dev/v1/players/{tag_formatted}/battlelog"
    headers = {"Authorization": f"Bearer {BRAWL_API_TOKEN}"}
    
    response = requests.get(url, headers=headers)
    if response.status_code != 200:
        return False
        
    battles = response.json().get("items", [])
    
    # 批次寫入資料庫，避免重複
    for battle in battles:
        battle_time = battle.get("battleTime")
        try:
            existing = supabase.table("battlelog").select("id").eq("battle_time", battle_time).eq("account", target_tag).execute()
            if len(existing.data) > 0:
                continue
        except:
            continue
            
        b = battle.get("battle", {})
        event = battle.get("event", {})
        my_brawler = ""
        brawler_trophies = ""
        
        players_list = []
        if "teams" in b:
            for team in b["teams"]:
                players_list.extend(team)
        elif "players" in b:
            players_list = b["players"]
            
        for player in players_list:
            if player.get("tag") == target_tag:
                my_brawler = player.get("brawler", {}).get("name", "")
                brawler_trophies = str(player.get("brawler", {}).get("trophies", ""))

        new_record = {
            "account": target_tag,
            "battle_time": battle_time,
            "mode": event.get("mode", "unknown"),
            "map": event.get("map", "unknown"),
            "type": b.get("type", "unknown"),
            "my_brawler": my_brawler,
            "brawler_trophies": brawler_trophies,
            "result": b.get("result", "draw"),
            "trophy_change": str(b.get("trophyChange", 0))
        }
        try:
            supabase.table("battlelog").insert(new_record).execute()
        except:
            pass
            
    return target_tag

# 3. 網頁主畫面 (結合搜尋功能與 Tailwind CSS)
@app.get("/")
def read_root(tag: str = ""):
    if not supabase:
        return HTMLResponse("<h1 style='color:red;'>系統連線失敗，請檢查資料庫變數</h1>")

    # HTML 前置與 CSS 框架 (Tailwind)
    html_head = """
    <!DOCTYPE html>
    <html lang="zh-TW">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Brawl Tracker 戰術主控台</title>
        <script src="https://cdn.tailwindcss.com"></script>
        <link href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0/css/all.min.css" rel="stylesheet">
    </head>
    <body class="bg-slate-950 text-slate-200 font-sans min-h-screen">
        <!-- 導覽列 -->
        <nav class="bg-slate-900 border-b border-slate-800 p-4 sticky top-0 z-50 shadow-lg">
            <div class="max-w-6xl mx-auto flex justify-between items-center">
                <a href="/" class="text-2xl font-black text-transparent bg-clip-text bg-gradient-to-r from-emerald-400 to-cyan-500">
                    <i class="fa-solid fa-gamepad mr-2"></i>Brawl Tracker
                </a>
            </div>
        </nav>
        
        <div class="max-w-6xl mx-auto p-6 mt-8">
            <!-- 搜尋區塊 -->
            <div class="bg-slate-900 rounded-2xl p-8 shadow-2xl border border-slate-800 mb-10 text-center">
                <h1 class="text-3xl font-bold mb-4">查詢玩家戰績</h1>
                <p class="text-slate-400 mb-6">輸入玩家標籤 (例如: #8UQL28V)，系統將自動更新並載入最新對戰紀錄。</p>
                <form action="/" method="GET" class="flex justify-center max-w-lg mx-auto">
                    <input type="text" name="tag" placeholder="輸入玩家標籤 (含 #)" required value="{}" 
                           class="w-full px-5 py-3 rounded-l-lg bg-slate-950 border border-slate-700 text-white focus:outline-none focus:border-emerald-500 focus:ring-1 focus:ring-emerald-500 uppercase">
                    <button type="submit" class="bg-emerald-500 hover:bg-emerald-600 text-slate-950 font-bold px-6 py-3 rounded-r-lg transition duration-200">
                        <i class="fa-solid fa-magnifying-glass"></i> 追蹤
                    </button>
                </form>
            </div>
    """.format(tag.upper())

    html_content = ""

    # 如果使用者有輸入 tag，就啟動爬蟲並顯示結果
    if tag:
        formatted_tag = fetch_and_save_data(tag)
        
        if formatted_tag:
            # 從資料庫撈取該玩家最新的 25 筆資料
            res = supabase.table("battlelog").select("*").eq("account", formatted_tag).order("battle_time", desc=True).limit(25).execute()
            data = res.data
            
            if len(data) > 0:
                html_content += f"""
                <div class="mb-4 flex justify-between items-end">
                    <h2 class="text-2xl font-bold text-white"><span class="text-emerald-400">{formatted_tag}</span> 的近期戰報</h2>
                    <span class="text-slate-400 text-sm">顯示最新 25 筆紀錄</span>
                </div>
                <div class="bg-slate-900 rounded-xl overflow-hidden border border-slate-800 shadow-xl">
                    <div class="overflow-x-auto">
                        <table class="w-full text-left border-collapse">
                            <thead>
                                <tr class="bg-slate-950/50 text-slate-400 text-sm uppercase tracking-wider">
                                    <th class="p-4 font-semibold">結果</th>
                                    <th class="p-4 font-semibold">英雄</th>
                                    <th class="p-4 font-semibold">模式 / 地圖</th>
                                    <th class="p-4 font-semibold">獎盃變化</th>
                                    <th class="p-4 font-semibold">時間</th>
                                </tr>
                            </thead>
                            <tbody class="divide-y divide-slate-800">
                """
                
                for row in data:
                    result = row.get('result', '')
                    
                    # 根據勝負決定視覺顏色
                    if result == "victory":
                        badge_color = "bg-emerald-500/10 text-emerald-400 border-emerald-500/20"
                        icon = "<i class='fa-solid fa-trophy'></i> 勝利"
                        trophy_color = "text-emerald-400"
                        trophy_change = f"+{row.get('trophy_change')}" if str(row.get('trophy_change')) != "0" else "0"
                    elif result == "defeat":
                        badge_color = "bg-rose-500/10 text-rose-400 border-rose-500/20"
                        icon = "<i class='fa-solid fa-skull'></i> 戰敗"
                        trophy_color = "text-rose-400"
                        trophy_change = row.get('trophy_change')
                    else:
                        badge_color = "bg-slate-500/10 text-slate-400 border-slate-500/20"
                        icon = "<i class='fa-solid fa-handshake'></i> 平手"
                        trophy_color = "text-slate-400"
                        trophy_change = row.get('trophy_change')

                    html_content += f"""
                                <tr class="hover:bg-slate-800/50 transition duration-150">
                                    <td class="p-4">
                                        <span class="px-3 py-1 rounded-full text-sm font-bold border {badge_color}">{icon}</span>
                                    </td>
                                    <td class="p-4 font-bold text-white">
                                        {row.get('my_brawler')}
                                    </td>
                                    <td class="p-4">
                                        <div class="text-white font-medium">{row.get('mode').capitalize()}</div>
                                        <div class="text-slate-400 text-sm">{row.get('map')}</div>
                                    </td>
                                    <td class="p-4 font-black {trophy_color} text-lg">
                                        {trophy_change}
                                    </td>
                                    <td class="p-4 text-slate-400 text-sm font-mono">
                                        {row.get('battle_time')}
                                    </td>
                                </tr>
                    """
                html_content += """
                            </tbody>
                        </table>
                    </div>
                </div>
                """
            else:
                html_content += "<div class='text-center p-10 bg-slate-900 rounded-xl'><p class='text-xl text-slate-400'>目前資料庫沒有這個標籤的戰績。請確認標籤是否正確。</p></div>"
        else:
            html_content += "<div class='text-center p-10 bg-rose-900/20 rounded-xl border border-rose-500/30'><p class='text-xl text-rose-400'>無法從 Supercell 獲取資料，請檢查玩家標籤是否正確！</p></div>"

    html_footer = """
        </div>
    </body>
    </html>
    """
    return HTMLResponse(content=html_head + html_content + html_footer)
