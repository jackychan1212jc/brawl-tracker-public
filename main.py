import os
import requests
import traceback
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from supabase import create_client, Client

app = FastAPI()

SUPABASE_URL = os.environ.get("SUPABASE_URL", "").strip()
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "").strip()
BRAWL_API_TOKEN = os.environ.get("BRAWL_API_TOKEN", "").strip()

try:
    supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
except Exception as e:
    supabase = None

def fetch_and_save_data(target_tag: str):
    if not supabase or not BRAWL_API_TOKEN:
        return False, "伺服器未綁定 Supabase 或 API 金鑰。"

    target_tag = target_tag.strip().upper()
    if not target_tag.startswith("#"):
        target_tag = "#" + target_tag
        
    tag_formatted = target_tag.replace("#", "%23")
    url = f"https://bsproxy.royaleapi.dev/v1/players/{tag_formatted}/battlelog"
    headers = {"Authorization": f"Bearer {BRAWL_API_TOKEN}"}
    
    try:
        response = requests.get(url, headers=headers)
        if response.status_code != 200:
            return False, f"無法連線到 Supercell API，狀態碼: {response.status_code}"
    except Exception as e:
        return False, f"網路請求發生例外錯誤: {str(e)}"
        
    battles = response.json().get("items", [])
    if not battles:
        return target_tag, "API 連線成功，但該玩家近期沒有任何對戰紀錄。"
    
    inserted_count = 0
    for battle in battles:
        try:
            battle_time = battle.get("battleTime")
            if not battle_time: continue
            
            existing = supabase.table("battlelog").select("id").eq("battle_time", battle_time).eq("account", target_tag).execute()
            if len(existing.data) > 0:
                continue
                
            # 🔥 破解排位賽的 null 陷阱
            b = battle.get("battle") or {}
            event = battle.get("event") or {}
            
            my_brawler = "未知"
            brawler_trophies = "0"
            
            players_list = []
            if "teams" in b:
                for team in b["teams"]:
                    players_list.extend(team)
            elif "players" in b:
                players_list = b["players"]
                
            for player in players_list:
                if player.get("tag") == target_tag:
                    b_data = player.get("brawler") or {}
                    my_brawler = b_data.get("name", "未知")
                    brawler_trophies = str(b_data.get("trophies", "0"))

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
            supabase.table("battlelog").insert(new_record).execute()
            inserted_count += 1
            
        except Exception as e:
            # 這次不沉默了，直接把錯誤回傳給網頁！
            return False, f"資料庫寫入時發生錯誤: {str(e)}"
            
    return target_tag, f"系統更新完畢！本次成功寫入 {inserted_count} 筆新戰績。"

@app.get("/")
def read_root(tag: str = ""):
    if not supabase:
        return HTMLResponse("<h1 style='color:red;'>系統連線失敗，請檢查資料庫變數</h1>")

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
        <nav class="bg-slate-900 border-b border-slate-800 p-4 sticky top-0 z-50 shadow-lg">
            <div class="max-w-6xl mx-auto flex justify-between items-center">
                <a href="/" class="text-2xl font-black text-transparent bg-clip-text bg-gradient-to-r from-emerald-400 to-cyan-500">
                    <i class="fa-solid fa-gamepad mr-2"></i>Brawl Tracker
                </a>
            </div>
        </nav>
        
        <div class="max-w-6xl mx-auto p-6 mt-8">
            <div class="bg-slate-900 rounded-2xl p-8 shadow-2xl border border-slate-800 mb-10 text-center">
                <h1 class="text-3xl font-bold mb-4">查詢玩家戰績</h1>
                <form action="/" method="GET" class="flex justify-center max-w-lg mx-auto">
                    <input type="text" name="tag" placeholder="輸入玩家標籤 (含 #)" required value="{}" 
                           class="w-full px-5 py-3 rounded-l-lg bg-slate-950 border border-slate-700 text-white focus:outline-none focus:border-emerald-500 uppercase">
                    <button type="submit" class="bg-emerald-500 hover:bg-emerald-600 text-slate-950 font-bold px-6 py-3 rounded-r-lg transition duration-200">
                        追蹤
                    </button>
                </form>
            </div>
    """.format(tag.upper())

    html_content = ""

    if tag:
        result_tag, system_msg = fetch_and_save_data(tag)
        
        # 把系統狀態顯示在畫面上，讓我們知道發生了什麼事
        if result_tag:
            html_content += f"<div class='mb-6 p-4 bg-emerald-900/30 border border-emerald-500/30 text-emerald-400 rounded-lg text-center font-bold'>✅ {system_msg}</div>"
            
            res = supabase.table("battlelog").select("*").eq("account", result_tag).order("battle_time", desc=True).limit(25).execute()
            data = res.data
            
            if len(data) > 0:
                html_content += f"""
                <div class="mb-4 flex justify-between items-end">
                    <h2 class="text-2xl font-bold text-white"><span class="text-emerald-400">{result_tag}</span> 的近期戰報</h2>
                </div>
                <div class="bg-slate-900 rounded-xl overflow-hidden border border-slate-800 shadow-xl">
                    <div class="overflow-x-auto">
                        <table class="w-full text-left border-collapse">
                            <thead>
                                <tr class="bg-slate-950/50 text-slate-400 text-sm uppercase tracking-wider">
                                    <th class="p-4 font-semibold">結果</th>
                                    <th class="p-4 font-semibold">英雄</th>
                                    <th class="p-4 font-semibold">模式 / 地圖</th>
                                    <th class="p-4 font-semibold">時間</th>
                                </tr>
                            </thead>
                            <tbody class="divide-y divide-slate-800">
                """
                for row in data:
                    result = row.get('result', '')
                    if result == "victory": badge = "<span class='text-emerald-400'>勝利</span>"
                    elif result == "defeat": badge = "<span class='text-rose-400'>戰敗</span>"
                    else: badge = "<span class='text-slate-400'>平手</span>"

                    html_content += f"""
                                <tr class="hover:bg-slate-800/50 transition duration-150">
                                    <td class="p-4 font-bold">{badge}</td>
                                    <td class="p-4 font-bold text-white">{row.get('my_brawler')}</td>
                                    <td class="p-4">
                                        <div class="text-white font-medium">{row.get('mode')}</div>
                                        <div class="text-slate-400 text-sm">{row.get('map')}</div>
                                    </td>
                                    <td class="p-4 text-slate-400 text-sm">{row.get('battle_time')}</td>
                                </tr>
                    """
                html_content += "</tbody></table></div></div>"
            else:
                html_content += "<div class='text-center p-10 bg-slate-900 rounded-xl'><p class='text-xl text-slate-400'>資料庫為空，沒有符合條件的紀錄。</p></div>"
        else:
            # 如果失敗，直接印出紅色錯誤訊息
            html_content += f"<div class='text-center p-10 bg-rose-900/20 rounded-xl border border-rose-500/30'><p class='text-xl text-rose-400'>❌ 發生錯誤：{system_msg}</p></div>"

    html_footer = "</div></body></html>"
    return HTMLResponse(content=html_head + html_content + html_footer)
