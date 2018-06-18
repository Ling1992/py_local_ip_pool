#!/usr/bin/env python
# -*- coding: utf-8 -*-
import configparser
import pyssdb
import time
import pymysql
import requests
import sys
import threading
from common import helper
import json


def pull_ips_thread():
    page = 1
    while helper.if_exists_pid_file():
        if ssdb.qsize(ssdb_queue_ip_pool) <= 100:
            get_ip(page)
            page += 1
        else:
            time.sleep(60)


def get_ip(page):
    # 直接操作数据库
    cursor = mysql.cursor()
    try:
        cursor.execute(select_ips_sql.format((page-1)*page_size, page_size))
        ips = cursor.fetchall()
        if len(ips) <= 1:
            raise Exception('没有ip 了 ，没有数据直接退出 ')
        for ip in ips:
            # 保存 ip 到ssdb  1、判断是否存在， 不存在则保存，否则跳过
            ip_id = ip[0]

            if ssdb.exists(ssdb_kv_black_list.format(ip_id)) == b'0':
                host = ip[1]
                port = ip[2]
                ip_type = ip[3]

                # 缓存两天
                ssdb.setx(ssdb_kv_black_list.format(ip_id),
                          '{}://{}:{}'.format(ip_type, host, port), 60 * 60 * 24 * 2)
                ssdb.qpush(ssdb_queue_ip_pool, json.dumps({'id': ip_id, 'host': host, 'port': port, 'type': ip_type}))
    except Exception as e:
        raise e
    finally:
        cursor.close()


def check_thread():
    while helper.if_exists_pid_file():
        res = ssdb.scan(ssdb_kv_black_list_check.format(''), '', -1)
        if len(res) >= 1:
            for i, re in enumerate(res[::2]):
                ip_id = str(re).split(':', -1)[-1]
                key = re
                value = res[i*2+1]
                check(key, ip_id, value)
        else:
            time.sleep(60*30)


def check(key, ip_id, value):
    # 使用代理 去请求 check_url
    proxies = {"http": value, "https": value}
    response = requests.get(check_url, proxies=proxies)
    if response.status_code == 200:
        pass
    elif response.status_code == 403 or response.status_code == 503:
        print('check : 代理{} 被{}限制 !!!!'.format(value, check_url))
        # 限制 5分钟
        time.sleep(60*5)
    else:
        # 反馈直接连接服务器 直接操作数据库
        cursor = mysql.cursor()
        try:
            cursor.execute(update_ip_sql.format(ip_id))
        except Exception as e:
            raise e
        finally:
            cursor.close()
        pass
    # 将ip 从 list 中移除
    ssdb.delete(key)


if __name__ == '__main__':

    project_name = sys.argv[1]
    print('project_name: {}'.format(project_name))

    # 预处理 pid文件
    helper.set_pid_file('_to_{}'.format(project_name))
    if helper.if_exists_pid_file():
        helper.delete_pid_file()
        time.sleep(60)
    helper.create_pid_file()

    # 初始化 config ssdb mysql
    config = configparser.ConfigParser()
    config.read(filenames='config/config.ini', encoding='utf-8')

    ssdb = pyssdb.Client(config.get('local', 'ssdb_host'), config.getint('local', 'ssdb_port'))

    mysql = pymysql.Connect(host=config.get('server', 'mysql_host'),
                            port=config.getint('server', 'mysql_port'),
                            database=config.get('server', 'mysql_db'),
                            user=config.get('server', 'mysql_user'),
                            password=config.get('server', 'mysql_password'))
    # config 变量
    # ip 池
    ssdb_queue_ip_pool = (config.get('local', 'ssdb_queue_ip_pool')).format(project_name)

    # ip 黑名单 2天内不再使用
    ssdb_kv_black_list = (config.get('local', 'ssdb_kv_black_list')).format(project_name) + '{}'

    # 本地验证
    ssdb_kv_black_list_check = (config.get('local', 'ssdb_kv_black_list_check')).format(project_name) + '{}'

    # check_url
    check_url = config.get('local', 'check_url')

    # sql
    select_ips_sql = "SELECT id, host, port, type FROM collect_ips WHERE status = 1 LIMIT {}, {}"
    update_ip_sql = "UPDATE collect_ips SET status = 0 WHERE id = {}"

    ping_sql = "SELECT * from collect_ips"

    page_size = 10

    # 多线程
    t1 = threading.Thread(target=pull_ips_thread)
    t2 = threading.Thread(target=check_thread)

    t1.start()
    t2.start()

    t1.join()
    t2.join()

    mysql.close()
    ssdb.disconnect()
    pass
