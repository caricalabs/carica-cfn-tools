import collections
import subprocess
import sys
import urllib.parse


def get_s3_https_url(region, bucket, key):
    if region == 'us-east-1':
        host = 's3'
    else:
        host = 's3-' + region
    return f'https://{host}.amazonaws.com/{bucket}/{key}'


def get_cfn_console_url(region, stack_arn, change_set_arn):
    """
    Get is a URL for the "new" (as of 2018-11) CloudFormation console to view
    the specified change set ARN in the specified stack.
    """
    # Must quote with "safe" set to exclude '/' so slashes in the ARNs get escaped as well.
    quoted_stack_arn = urllib.parse.quote(stack_arn, safe='')
    quoted_change_set_arn = urllib.parse.quote(change_set_arn, safe='')

    return f'https://console.aws.amazon.com/cloudformation/home?region={region}#' \
           f'/stacks/{quoted_stack_arn}/changesets/{quoted_change_set_arn}/changes'


def open_url_in_browser(url):
    print()
    print(url)
    if sys.platform == 'darwin':
        command = 'open'
    else:
        command = 'xdg-open'
    subprocess.Popen([command, url]).communicate()


def update_dict(d, u):
    for k, v in u.items():
        if isinstance(v, collections.Mapping):
            d[k] = update_dict(d.get(k, {}), v)
        else:
            d[k] = v
    return d
