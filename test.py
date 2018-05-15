#!/usr/bin/env python
# -*- coding: utf-8 -*-
import configparser
import pyssdb
import time
import pymysql
import requests
import sys
from common import helper

if __name__ == '__main__':
    project_name = 'local_ip_pool'
    helper.set_pid_file('_to_{}'.format(project_name))
    helper.create_pid_file()
    time.sleep(20)
    helper.delete_pid_file()
    pass



