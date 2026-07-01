#!/usr/bin/env python3
"""
运行Twitter抓取脚本
"""
import subprocess
import sys
import os

# 设置工作目录
work_dir = '/Users/qiqi/.qwenpaw/workspaces/github-manager/style-source'
os.chdir(work_dir)

# Twitter URL
twitter_url = "https://x.com/iamaiistudio/status/2072208469437112566?s=20"

print("=== 开始抓取Twitter页面 ===")
print(f"URL: {twitter_url}")

# 运行抓取脚本
try:
    result = subprocess.run([
        sys.executable, 
        'scripts/fetch_twitter.py', 
        twitter_url
    ], capture_output=True, text=True, timeout=60)
    
    print("=== 抓取结果 ===")
    print(result.stdout)
    if result.stderr:
        print("=== 错误信息 ===")
        print(result.stderr)
    
    # 检查是否成功
    if result.returncode == 0:
        print("✅ 抓取完成")
    else:
        print(f"❌ 抓取失败，返回码: {result.returncode}")
        
except subprocess.TimeoutExpired:
    print("❌ 抓取超时")
except Exception as e:
    print(f"❌ 执行错误: {e}")