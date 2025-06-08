import requests
import json
import os
import time
from datetime import datetime

# --- 配置 ---
DATA_DIR = "data"
DATA_FILE = os.path.join(DATA_DIR, "bilibili_popular_cache.json")
NUM_PAGES_TO_FETCH = 4  # 获取多少页热门视频，每页50个 (总共 4*50=200个视频作为候选)
PAGE_SIZE = 50          # B站API每页数量，热门API通常支持最大50
TOP_N_VIDEOS = 50       # 输出增长最快的多少个视频 (你可以根据需要调整这个数值)

# 增长评分权重 (一个数据的增长代表多少分数，可根据偏好调整)
W_VIEW_GROWTH = 1       # 1个播放 = 1分
W_LIKE_GROWTH = 5       # 1个点赞 = 5分
W_DANMAKU_GROWTH = 10   # 1条弹幕 = 10分
W_REPLY_GROWTH = 20     # 1条评论 = 20分
W_FAVORITE_GROWTH = 30  # 1个收藏 = 30分
W_SHARE_GROWTH = 40     # 1次分享 = 40分
W_COIN_GROWTH = 100     # 1个投币 = 100分 (最高价值)

# 【重要】请填入您自己的B站Cookie。这对于稳定访问API至关重要，可有效避免被风控。
# 获取方法：登录bilibili.com -> F12打开开发者工具 -> Network -> 刷新页面 -> 找到任意一个 b站的请求 -> Headers -> 找到 cookie, 复制其完整的字符串值。
# 例如: COOKIE = "SESSDATA=xxxx; bili_jct=xxxx; ..."
COOKIE = "5f32783a%2C1764905343%2Ca2d93%2A61CjBp0SU9SdZxNRmtGEppBVoIgGSJaActF_ZPkeSV4LzfU7GhfitNyim9hMU6n68gQXoSVnhpUmFpekQwVzdPQ3ZUQ3VvMmZzaVVsRmYyQ3NUY1cwakg1bm5PNk9BQ1pVaHgzdF9OVkJCdldSSUVBYzc0VU9qakM2RHEwU3ZvMnJqWWtmTzVGMnVRIIEC"

# --- 功能函数 ---

def ensure_dir(directory_path):
    """确保指定的目录存在，如果不存在则创建它。"""
    if not os.path.exists(directory_path):
        try:
            os.makedirs(directory_path)
            print(f"目录已创建: {directory_path}")
        except OSError as e:
            print(f"创建目录失败: {directory_path}, 错误: {e}")
            raise # 如果无法创建关键目录，则抛出异常

def fetch_popular_videos(pages=NUM_PAGES_TO_FETCH, page_size=PAGE_SIZE):
    """通过B站API获取多页热门视频数据。"""
    print(f"开始从B站获取热门视频数据，共 {pages} 页，每页 {page_size} 个...")
    all_videos_list = []
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
        'Accept': 'application/json, text/plain, */*',
        'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
        'Accept-Encoding': 'gzip, deflate, br',
        'Origin': 'https://www.bilibili.com',
        'Referer': 'https://www.bilibili.com/v/popular/all/',
        'Connection': 'keep-alive',
    }
    if COOKIE:
        headers['Cookie'] = COOKIE

    for page_num in range(1, pages + 1):
        url = "https://api.bilibili.com/x/web-interface/popular"
        try:
            response = requests.get(url, headers=headers, timeout=15) # 设置超时
            response.raise_for_status()  # HTTP错误状态码会抛出异常
            api_data = response.json()

            if api_data.get("code") == 0:
                videos_on_page = api_data.get("data", {}).get("list", [])
                if not videos_on_page:
                    print(f"警告: 第 {page_num} 页未返回视频数据。可能已无更多内容。")
                    break 
                all_videos_list.extend(videos_on_page)
                print(f"成功获取第 {page_num} 页数据，获得 {len(videos_on_page)} 个视频。")
                if page_num < pages: # 不是最后一页时才休眠
                    time.sleep(1.5) # 友好请求，避免过于频繁，休眠1.5秒
            else:
                print(f"API请求错误 (第 {page_num} 页): Code {api_data.get('code')}, Message: {api_data.get('message', '未知API错误')}")
                # 可以选择在此处返回None或部分数据，或继续尝试下一页
                # 为简单起见，如果一页失败，我们可能不希望整个过程失败，但需记录
                # return None 
        except requests.exceptions.Timeout:
            print(f"网络请求超时 (第 {page_num} 页，URL: {url})")
            # return None
        except requests.exceptions.RequestException as e:
            print(f"网络请求发生错误 (第 {page_num} 页): {e}")
            # return None
        except json.JSONDecodeError:
            print(f"解析JSON响应失败 (第 {page_num} 页)。响应内容: {response.text[:200]}...") # 打印部分响应内容帮助调试
            # return None
    
    print(f"数据获取完成，总共获得 {len(all_videos_list)} 个视频。")
    return all_videos_list

def load_previous_video_stats(filepath):
    """从JSON文件加载上一小时记录的视频统计数据。"""
    if not os.path.exists(filepath):
        print(f"未找到旧数据文件: {filepath}")
        return {}
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)
            print(f"成功从 {filepath} 加载 {len(data)} 条旧视频数据。")
            return data
    except (IOError, json.JSONDecodeError) as e:
        print(f"加载旧数据文件 {filepath} 失败: {e}")
        return {} # 若加载失败，返回空字典，效果类似首次运行

def save_current_video_stats(filepath, video_stats_data):
    """将当前获取的视频统计数据保存到JSON文件，供下次比较。"""
    try:
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(video_stats_data, f, ensure_ascii=False, indent=4)
        print(f"当前视频数据 ({len(video_stats_data)} 条) 已成功保存至: {filepath}")
    except IOError as e:
        print(f"保存当前视频数据至 {filepath} 失败: {e}")

def calculate_growth_and_rank_videos(current_video_list, previous_video_stats):
    """
    计算视频的各项互动数据增长，并根据加权增长分进行排名。
    current_video_list: 从API获取的原始视频对象列表。
    previous_video_stats: 字典，键为bvid，值为包含各项统计数据的字典。
    返回: (排名后的增长视频列表, 当前所有视频的统计数据用于保存)
    """
    videos_with_growth_data = []
    current_stats_to_be_saved = {} 

    # --- 重新引入并优化的去重逻辑 ---
    print(f"原始获取视频 {len(current_video_list)} 条，开始去重...")
    unique_videos = {}
    for video in current_video_list:
        bvid = video.get("bvid")
        # 总是保留最后出现的版本，因为它包含了最新的数据
        if bvid:
            unique_videos[bvid] = video
    
    deduplicated_video_list = list(unique_videos.values())
    print(f"去重后，得到 {len(deduplicated_video_list)} 个独立视频进行分析。")
    # --- 去重结束 ---

    print("开始分析视频数据并计算增长...")
    for video_data in deduplicated_video_list: # 使用去重后的列表
        bvid = video_data.get("bvid")
        if not bvid: # 跳过没有bvid的数据（理论上不应发生）
            continue

        title = video_data.get("title", "未知标题")
        owner = video_data.get("owner", {})
        uploader_name = owner.get("name", "N/A")
        uploader_followers = owner.get("stat", {}).get("follower", 0)

        stat = video_data.get("stat", {})
        current_view_count = stat.get("view", 0)
        current_like_count = stat.get("like", 0)
        current_danmaku_count = stat.get("danmaku", 0)
        current_reply_count = stat.get("reply", 0)
        current_favorite_count = stat.get("favorite", 0)
        current_share_count = stat.get("share", 0)
        current_coin_count = stat.get("coin", 0)

        # 准备本次运行时获取到的所有视频的最新数据，用于保存
        current_stats_to_be_saved[bvid] = {
            "title": title,
            "view": current_view_count,
            "like": current_like_count,
            "danmaku": current_danmaku_count,
            "reply": current_reply_count,
            "favorite": current_favorite_count,
            "share": current_share_count,
            "coin": current_coin_count,
        }

        # 只有当视频存在于上一次的记录中时，才计算增长
        if bvid in previous_video_stats:
            previous_stat = previous_video_stats[bvid]
            
            # 计算各项指标的增长
            view_growth = current_view_count - previous_stat.get("view", 0)
            like_growth = current_like_count - previous_stat.get("like", 0)
            danmaku_growth = current_danmaku_count - previous_stat.get("danmaku", 0)
            reply_growth = current_reply_count - previous_stat.get("reply", 0)
            favorite_growth = current_favorite_count - previous_stat.get("favorite", 0)
            share_growth = current_share_count - previous_stat.get("share", 0)
            coin_growth = current_coin_count - previous_stat.get("coin", 0)

            # 避免负增长计入（可能由于B站数据调整或视频状态变更）
            if view_growth < 0: view_growth = 0
            if like_growth < 0: like_growth = 0
            if danmaku_growth < 0: danmaku_growth = 0
            if reply_growth < 0: reply_growth = 0
            if favorite_growth < 0: favorite_growth = 0
            if share_growth < 0: share_growth = 0
            if coin_growth < 0: coin_growth = 0

            # 计算综合增长得分
            total_growth_score = (
                (view_growth * W_VIEW_GROWTH) +
                (like_growth * W_LIKE_GROWTH) +
                (danmaku_growth * W_DANMAKU_GROWTH) +
                (reply_growth * W_REPLY_GROWTH) +
                (favorite_growth * W_FAVORITE_GROWTH) +
                (share_growth * W_SHARE_GROWTH) +
                (coin_growth * W_COIN_GROWTH)
            )

            # 确认机会指数基于总评论数
            opportunity_index = view_growth / (current_reply_count + 1)

            # 计算最终引流机会分 (综合分 * 机会指数)
            final_score = total_growth_score * opportunity_index

            if total_growth_score > 0: # 只考虑有正增长的视频
                videos_with_growth_data.append({
                    "bvid": bvid,
                    "title": title,
                    "link": f"https://www.bilibili.com/video/{bvid}",
                    "final_score": final_score,
                    "opportunity_index": opportunity_index,
                    "growth_score": total_growth_score,
                    "uploader_name": uploader_name,
                    "total_view": current_view_count,
                    "total_reply": current_reply_count,
                    "delta_view": view_growth,
                    "delta_like": like_growth,
                    "delta_reply": reply_growth,
                    "delta_danmaku": danmaku_growth,
                    "delta_favorite": favorite_growth,
                    "delta_share": share_growth,
                    "delta_coin": coin_growth,
                })
    
    # 按最终引流机会分从高到低排序
    videos_with_growth_data.sort(key=lambda x: x["final_score"], reverse=True)
    
    if videos_with_growth_data:
        print(f"计算完成，共 {len(videos_with_growth_data)} 个视频产生正增长。")
    else:
        print("计算完成，没有视频产生正增长，或者所有视频都是新上榜。")
        
    return videos_with_growth_data, current_stats_to_be_saved

def display_top_growing_videos(top_videos_list, count=TOP_N_VIDEOS):
    """格式化并显示增长最快的Top N视频列表。"""
    if not top_videos_list:
        print("没有可供显示的增长视频数据。")
        return

    num_to_display = min(count, len(top_videos_list))
    print("\n" + f"--- B站热门视频每小时增长趋势 Top {num_to_display} ---")
    print(f"--- (数据截至: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}) ---")
    
    # 动态计算标题栏宽度以适应内容
    # 标题最大长度设为40个字符，BV号12，增长和分数各8字符，排名3字符，加间隔
    # Rank | Title (40) | BVID (12) | View+ | Like+ | Score
    # 3    | 40         | 12        | 8     | 8     | 8   = 79 + 5 spaces = 84
    header_format = f"{'排名':<4}{'标题':<42}{'BV号':<14}{'播放+':<10}{'点赞+':<10}{'弹幕+':<10}{'评论+':<10}{'收藏+':<10}{'投币+':<10}{'分享+':<10}{'机会指数':<10}{'引流分':<10}"
    print(header_format)
    # 根据格式调整分割线长度
    print("-" * (4 + 42 + 14 + 10 * 9 + 5)) 

    for index, video_info in enumerate(top_videos_list[:num_to_display], 1):
        row_format = (
            f"{index:<4}"
            f"{video_info['title'][:40]:<42}"
            f"{video_info['bvid']:<14}"
            f"{video_info['delta_view']:<10,}"
            f"{video_info['delta_like']:<10,}"
            f"{video_info['delta_danmaku']:<10,}"
            f"{video_info['delta_reply']:<10,}"
            f"{video_info['delta_favorite']:<10,}"
            f"{video_info['delta_coin']:<10,}"
            f"{video_info['delta_share']:<10,}"
            f"{video_info['opportunity_index']:<10.1f}"
            f"{video_info['final_score']:<10.0f}"
        )
        print(row_format)

def generate_html_report(top_videos_list, filename="bilibili_hot_report.html", count=50):
    """根据视频增长数据生成一个HTML报告文件。"""
    
    # 开始HTML内容，包含CSS样式
    html_head = f"""
    <!DOCTYPE html>
    <html lang="zh-CN">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>B站热门增长趋势报告</title>
        <style>
            body {{
                font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
                background-color: #f0f2f5;
                color: #333;
                margin: 0;
                padding: 20px;
            }}
            .container {{
                max-width: 1200px;
                margin: auto;
                background: #fff;
                padding: 25px 30px;
                border-radius: 12px;
                box-shadow: 0 6px 12px rgba(0,0,0,0.08);
            }}
            h1 {{
                color: #00a1d6; /* B站蓝 */
                text-align: center;
                border-bottom: 2px solid #e7e7e7;
                padding-bottom: 15px;
                margin-top: 0;
            }}
            p.timestamp {{
                text-align: center;
                color: #777;
                margin-bottom: 25px;
                font-size: 0.95em;
            }}
            table {{
                width: 100%;
                border-collapse: collapse;
                margin-top: 20px;
            }}
            th, td {{
                padding: 14px 18px;
                border: 1px solid #ddd;
                text-align: left;
                vertical-align: middle;
            }}
            thead th {{
                background-color: #00a1d6;
                color: white;
                font-weight: 600;
                position: sticky;
                top: 0;
            }}
            tbody tr:nth-child(even) {{
                background-color: #f9f9f9;
            }}
            tbody tr:hover {{
                background-color: #e9efff;
            }}
            a {{
                color: #fb7299; /* B站粉 */
                text-decoration: none;
                font-weight: 500;
            }}
            a:hover {{
                text-decoration: underline;
            }}
            .rank {{
                font-weight: bold;
                text-align: center;
                width: 5%;
            }}
            .growth-data {{
                text-align: right;
                font-family: 'Courier New', Courier, monospace;
                width: 9%;
            }}
            .title-col {{
                width: 35%;
            }}
            .uploader-col {{
                width: 15%;
            }}
        </style>
    </head>
    """

    # HTML主体内容
    html_body = f"""
    <body>
        <div class="container">
            <h1>B站热门视频每小时增长趋势 Top {min(count, len(top_videos_list)) if top_videos_list else 0}</h1>
            <p class="timestamp">报告生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
    """

    if not top_videos_list:
        html_body += "<p><strong>本周期内未监测到符合条件的视频增长，或正在等待第一个数据周期。</strong></p>"
    else:
        # 表格头部
        html_body += """
            <table>
                <thead>
                    <tr>
                        <th class="rank">排名</th>
                        <th class="title-col">标题</th>
                        <th class="uploader-col">UP主</th>
                        <th class="growth-data">总播放</th>
                        <th class="growth-data">播放+</th>
                        <th class="growth-data">评论+</th>
                        <th class="growth-data">机会指数</th>
                        <th class="growth-data"><strong>引流分</strong></th>
                    </tr>
                </thead>
                <tbody>
        """
        # 生成表格行
        num_to_display = min(count, len(top_videos_list))
        for index, video_info in enumerate(top_videos_list[:num_to_display], 1):
            html_body += f"""
                    <tr>
                        <td class="rank">{index}</td>
                        <td><a href="{video_info['link']}" target="_blank" title="{video_info['title']}">{video_info['title']}</a></td>
                        <td>{video_info.get('uploader_name', 'N/A')}</td>
                        <td class="growth-data">{video_info.get('total_view', 0):,}</td>
                        <td class="growth-data">{video_info.get('delta_view', 0):,}</td>
                        <td class="growth-data">{video_info.get('delta_reply', 0):,}</td>
                        <td class="growth-data">{video_info.get('opportunity_index', 0):.1f}</td>
                        <td class="growth-data"><strong>{video_info.get('final_score', 0):,.0f}</strong></td>
                    </tr>
            """
        html_body += """
                </tbody>
            </table>
        """
    
    # HTML结尾
    html_body += """
        </div>
    </body>
    </html>
    """
    
    html_content = html_head + html_body

    try:
        with open(filename, 'w', encoding='utf-8') as f:
            f.write(html_content)
        print(f"HTML报告已生成: {filename}")
    except IOError as e:
        print(f"生成HTML报告失败: {e}")

def main_monitoring_process():
    """主监控流程函数"""
    print(f"开始B站热门视频趋势监测 ({datetime.now().strftime('%Y-%m-%d %H:%M:%S')})")
    ensure_dir(DATA_DIR)

    # 1. 加载上一次记录的视频统计数据
    previous_stats = load_previous_video_stats(DATA_FILE)
    if not previous_stats:
        print("提示: 未找到或未能加载上周期数据。本次运行将主要用于收集基线数据。")
        print("增长趋势列表将在下个周期（约1小时后）的运行中开始生成。")
    
    # 2. 从API获取当前的热门视频数据
    current_raw_videos = fetch_popular_videos()
    if not current_raw_videos:
        print("错误: 未能从B站API获取到任何视频数据。程序将退出。")
        return

    # 3. 计算视频增长数据并排名，同时获取本次运行需要保存的统计数据
    ranked_videos_by_growth, current_stats_for_saving = calculate_growth_and_rank_videos(current_raw_videos, previous_stats)

    # 4. 如果 previous_stats 非空 (即非首次运行或数据加载成功)，则显示Top增长视频
    if previous_stats: # 只有在有历史数据对比时才显示增长榜
        if ranked_videos_by_growth:
            display_top_growing_videos(ranked_videos_by_growth, count=TOP_N_VIDEOS)
            generate_html_report(ranked_videos_by_growth, count=TOP_N_VIDEOS)
        else:
            print("虽然有历史数据，但本周期内未监测到符合条件的视频增长。")
            generate_html_report([], count=TOP_N_VIDEOS)
    else:
        # 首次运行时也生成一个提示性的HTML报告
        generate_html_report([], count=TOP_N_VIDEOS)
    
    # 5. 保存当前获取到的所有视频的最新统计数据，供下一次运行使用
    if current_stats_for_saving:
        save_current_video_stats(DATA_FILE, current_stats_for_saving)
    else:
        print("警告: 没有有效的当前视频数据可供保存。")

    print(f"本次监测运行结束 ({datetime.now().strftime('%Y-%m-%d %H:%M:%S')})。")

if __name__ == "__main__":
    main_monitoring_process() 