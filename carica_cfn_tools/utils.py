import os
import subprocess
import sys


def get_s3_https_url(region, bucket, key):
    if region == 'us-east-1':
        host = 's3'
    else:
        host = 's3-' + region
    return f'https://{host}.amazonaws.com/{bucket}/{key}'


def open_url_in_browser(url):
    print()
    print(url)
    if sys.platform == 'darwin':
        command = 'open'
    else:
        command = 'xdg-open'
    subprocess.Popen([command, url]).communicate()


def print_fs_tree(path):
    for root, _, files in os.walk(path):
        for file in files:
            relative_path = os.path.join(root, file)[len(path) + 1:]
            print('  ' + relative_path)
