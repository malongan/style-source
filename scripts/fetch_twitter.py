#!/usr/bin/env python3
"""
抓取Twitter/X页面内容并下载图片
"""
import sys
import json
import re
import urllib.request
import urllib.parse
from bs4 import BeautifulSoup

def fetch_twitter_content(url):
    """抓取Twitter页面内容"""
    try:
        # 设置请求头
        headers = {
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive',
        }
        
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=30) as response:
            html = response.read().decode('utf-8')
        
        # 尝试提取文本内容
        # Twitter页面通常有meta标签包含描述
        soup = BeautifulSoup(html, 'html.parser')
        
        # 尝试获取og:description或description
        description = ""
        og_desc = soup.find('meta', property='og:description')
        if og_desc:
            description = og_desc.get('content', '')
        
        if not description:
            meta_desc = soup.find('meta', attrs={'name': 'description'})
            if meta_desc:
                description = meta_desc.get('content', '')
        
        # 尝试提取推文文本
        tweet_text = ""
        # 查找包含推文文本的元素
        tweet_elements = soup.find_all('div', attrs={'data-testid': 'tweetText'})
        if tweet_elements:
            tweet_text = tweet_elements[0].get_text(strip=True)
        
        # 如果没有找到推文文本，尝试从脚本中提取
        if not tweet_text:
            # 查找包含推文数据的脚本
            scripts = soup.find_all('script')
            for script in scripts:
                script_text = script.string or ""
                if 'tweetText' in script_text:
                    # 尝试提取推文文本
                    match = re.search(r'"tweetText":"([^"]+)"', script_text)
                    if match:
                        tweet_text = match.group(1)
                        break
        
        # 提取图片URL
        image_urls = []
        # 查找og:image
        og_image = soup.find('meta', property='og:image')
        if og_image:
            image_urls.append(og_image.get('content', ''))
        
        # 查找所有图片
        img_tags = soup.find_all('img')
        for img in img_tags:
            src = img.get('src', '')
            if 'pbs.twimg.com' in src and 'profile_images' not in src:
                image_urls.append(src)
        
        return {
            'url': url,
            'description': description,
            'tweet_text': tweet_text,
            'image_urls': list(set(image_urls)),  # 去重
            'html_length': len(html)
        }
        
    except Exception as e:
        return {
            'url': url,
            'error': str(e),
            'image_urls': []
        }

def download_image(url, save_path):
    """下载图片"""
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Referer': 'https://twitter.com/',
        }
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=30) as response:
            with open(save_path, 'wb') as f:
                f.write(response.read())
        return True
    except Exception as e:
        print(f"下载图片失败: {e}")
        return False

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("用法: python fetch_twitter.py <twitter_url>")
        sys.exit(1)
    
    url = sys.argv[1]
    result = fetch_twitter_content(url)
    
    # 保存结果
    with open('/tmp/twitter_result.json', 'w', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    
    # 打印结果
    print("=== Twitter页面抓取结果 ===")
    print(f"URL: {result.get('url', 'N/A')}")
    if 'error' in result:
        print(f"错误: {result['error']}")
    else:
        print(f"HTML长度: {result.get('html_length', 0)} 字节")
        print(f"描述: {result.get('description', 'N/A')[:200]}")
        print(f"推文文本: {result.get('tweet_text', 'N/A')[:200]}")
        print(f"图片数量: {len(result.get('image_urls', []))}")
        for i, img_url in enumerate(result.get('image_urls', [])[:3]):
            print(f"  图片{i+1}: {img_url[:100]}...")
    
    # 下载第一张图片
    if result.get('image_urls'):
        first_image = result['image_urls'][0]
        save_path = '/tmp/style_preview.jpg'
        if download_image(first_image, save_path):
            print(f"\n✅ 图片已下载到: {save_path}")
        else:
            print(f"\n❌ 图片下载失败")
    else:
        print("\n⚠️ 未找到图片")