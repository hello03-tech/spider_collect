import argparse
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from loguru import logger
from apis.xhs_pc_apis import XHS_Apis
from xhs_utils.common_util import init
from xhs_utils.data_util import handle_note_info, download_note, save_to_xlsx, save_to_json
from xhs_utils.style_util import enrich_note_style


class Data_Spider():
    def __init__(self):
        self.xhs_apis = XHS_Apis()
        self.skip_style_analysis = os.getenv('SKIP_STYLE_ANALYSIS', '0').lower() in ('1', 'true', 'yes')

    def spider_note(self, note_url: str, cookies_str: str, proxies=None):
        """
        爬取一个笔记的信息
        :param note_url:
        :param cookies_str:
        :return:
        """
        note_info = None
        try:
            success, msg, note_info = self.xhs_apis.get_note_info(note_url, cookies_str, proxies)
            if success:
                note_info = note_info['data']['items'][0]
                note_info['url'] = note_url
                note_info = handle_note_info(note_info)
                if not self.skip_style_analysis:
                    note_info = enrich_note_style(note_info)
                try:
                    comment_success, comment_msg, notes_comment = self.xhs_apis.get_note_all_comment(
                        note_url, cookies_str, proxies
                    )
                    if comment_success:
                        note_info['comments'] = notes_comment
                    else:
                        note_info['comments'] = []
                        logger.warning(f'拉取评论失败 {note_url}: {comment_msg}')
                except Exception as exc:
                    note_info['comments'] = []
                    logger.warning(f'拉取评论异常 {note_url}: {exc}')
        except Exception as e:
            success = False
            msg = e
        logger.info(f'爬取笔记信息 {note_url}: {success}, msg: {msg}')
        return success, msg, note_info

    def spider_some_note(self, notes: list, cookies_str: str, base_path: dict, save_choice: str, output_name: str = '', worker_count: int = 1, proxies=None):
        """
        爬取一些笔记的信息
        :param notes:
        :param cookies_str:
        :param base_path:
        :param output_name: 保存文件的名称（用于excel/json）
        :return:
        """
        if save_choice in ('all', 'excel', 'json') and output_name == '':
            raise ValueError('output_name 不能为空')
        note_list = []
        if worker_count > 1:
            with ThreadPoolExecutor(max_workers=worker_count) as executor:
                future_to_url = {
                    executor.submit(self.spider_note, note_url, cookies_str, proxies): note_url
                    for note_url in notes
                }
                for future in as_completed(future_to_url):
                    url = future_to_url[future]
                    try:
                        success, msg, note_info = future.result()
                    except Exception as exc:
                        logger.warning(f'并发爬取 {url} 失败: {exc}')
                        continue
                    if note_info is not None and success:
                        note_list.append(note_info)
        else:
            for note_url in notes:
                success, msg, note_info = self.spider_note(note_url, cookies_str, proxies)
                if note_info is not None and success:
                    note_list.append(note_info)
        for note_info in note_list:
            if save_choice == 'all' or 'media' in save_choice:
                download_note(note_info, base_path['media'], save_choice)
        if save_choice == 'all' or save_choice == 'excel':
            file_path = os.path.abspath(os.path.join(base_path['excel'], f'{output_name}.xlsx'))
            save_to_xlsx(note_list, file_path)
        if save_choice == 'json':
            file_path = os.path.abspath(os.path.join(base_path['json'], f'{output_name}.json'))
            save_to_json(note_list, file_path)


    def spider_user_all_note(self, user_url: str, cookies_str: str, base_path: dict, save_choice: str, output_name: str = '', worker_count: int = 1, proxies=None):
        """
        爬取一个用户的所有笔记
        :param user_url:
        :param cookies_str:
        :param base_path:
        :param output_name: 保存文件的名称（用于excel/json）
        :return:
        """
        note_list = []
        try:
            success, msg, all_note_info = self.xhs_apis.get_user_all_notes(user_url, cookies_str, proxies)
            if success:
                logger.info(f'用户 {user_url} 作品数量: {len(all_note_info)}')
                for simple_note_info in all_note_info:
                    note_url = f"https://www.xiaohongshu.com/explore/{simple_note_info['note_id']}?xsec_token={simple_note_info['xsec_token']}"
                    note_list.append(note_url)
            if save_choice in ('all', 'excel', 'json') and output_name == '':
                output_name = user_url.split('/')[-1].split('?')[0]
            self.spider_some_note(note_list, cookies_str, base_path, save_choice, output_name, worker_count, proxies)
        except Exception as e:
            success = False
            msg = e
        logger.info(f'爬取用户所有视频 {user_url}: {success}, msg: {msg}')
        return note_list, success, msg

    def spider_some_search_note(self, query: str, require_num: int, cookies_str: str, base_path: dict, save_choice: str, sort_type_choice=0, note_type=0, note_time=0, note_range=0, pos_distance=0, geo: dict = None,  output_name: str = '', worker_count: int = 1, proxies=None):
        """
            指定数量搜索笔记，设置排序方式和笔记类型和笔记数量
            :param query 搜索的关键词
            :param require_num 搜索的数量
            :param cookies_str 你的cookies
            :param base_path 保存路径
            :param sort_type_choice 排序方式 0 综合排序, 1 最新, 2 最多点赞, 3 最多评论, 4 最多收藏
            :param note_type 笔记类型 0 不限, 1 视频笔记, 2 普通笔记
            :param note_time 笔记时间 0 不限, 1 一天内, 2 一周内天, 3 半年内
            :param note_range 笔记范围 0 不限, 1 已看过, 2 未看过, 3 已关注
            :param pos_distance 位置距离 0 不限, 1 同城, 2 附近 指定这个必须要指定 geo
            :param output_name: 保存文件的名称（用于excel/json）
            返回搜索的结果
        """
        note_list = []
        try:
            success, msg, notes = self.xhs_apis.search_some_note(query, require_num, cookies_str, sort_type_choice, note_type, note_time, note_range, pos_distance, geo, proxies)
            if success:
                notes = list(filter(lambda x: x['model_type'] == "note", notes))
                logger.info(f'搜索关键词 {query} 笔记数量: {len(notes)}')
                for note in notes:
                    note_url = f"https://www.xiaohongshu.com/explore/{note['id']}?xsec_token={note['xsec_token']}"
                    note_list.append(note_url)
            final_output_name = output_name or query
            if save_choice in ('all', 'excel', 'json') and not output_name:
                final_output_name = query
            self.spider_some_note(note_list, cookies_str, base_path, save_choice, final_output_name, worker_count, proxies)
        except Exception as e:
            success = False
            msg = e
        logger.info(f'搜索关键词 {query} 笔记: {success}, msg: {msg}')
        return note_list, success, msg

def parse_args():
    parser = argparse.ArgumentParser(
        description='Spider_XHS: Search XiaoHongShu notes by keyword and save the first N results.')
    parser.add_argument(
        '--query',
        '-q',
        default='视觉UI风格',
        help='搜索关键词，默认 "视觉UI风格"，可自定义。')
    parser.add_argument(
        '--count',
        '-n',
        type=int,
        default=10,
        help='需要爬取的笔记数量，默认为 10 条。')
    parser.add_argument(
        '--save',
        '-s',
        choices=['all', 'excel', 'json', 'media', 'media-image', 'media-video'],
        default='json',
        help='保存选项，默认为 json（只保存结构化 JSON，避免生成媒体/表格）。')
    parser.add_argument(
        '--workers',
        '-w',
        type=int,
        default=4,
        help='并发爬取笔记的线程数，默认为 4。')
    parser.add_argument(
        '--output-name',
        '-o',
        default='',
        help='输出文件的前缀（用于 Excel/JSON），默认自动使用关键词加时间戳。')
    return parser.parse_args()


def main():
    """
    程序入口，可通过命令行传入关键词和数量，默认爬取 "视觉UI风格" 相关的 10 条笔记信息。
    """
    args = parse_args()
    cookies_str, base_path = init()
    data_spider = Data_Spider()

    query = args.query.strip() or '视觉UI风格'
    count = max(1, args.count)
    output_name = args.output_name.strip()
    if not output_name:
        safe_query = query.replace(' ', '_')
        timestamp = time.strftime('%Y%m%d%H%M%S')
        output_name = f'{safe_query}_{timestamp}'
    worker_count = max(1, args.workers)
    data_spider.spider_some_search_note(
        query=query,
        require_num=count,
        cookies_str=cookies_str,
        base_path=base_path,
        save_choice=args.save,
        sort_type_choice=0,
        note_type=0,
        note_time=0,
        note_range=0,
        pos_distance=0,
        geo=None,
        output_name=output_name,
        worker_count=worker_count,
    )


if __name__ == '__main__':
    main()
