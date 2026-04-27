#!/usr/bin/env python3
"""
Bangla Subtitle M3U Playlist Generator for GitHub Actions
"""

import os
import sys
import json
import logging
import argparse
from pathlib import Path
from datetime import datetime
import requests
from bs4 import BeautifulSoup
import re
from urllib.parse import urljoin

# কনফিগারেশন
CONFIG = {
    "series": [
        {
            "name": "mehmed-the-greatest-conquerors",
            "url": "https://bangla-subtitle.com/mehmed-the-greatest-conquerors/",
            "display_name": "Mehmed: The Greatest Conquerors",
            "seasons": [1, 2, 3]
        },
        {
            "name": "childhoad-of-orhan-gazi", 
            "url": "https://bangla-subtitle.com/childhoad-of-orhan-gazi/",
            "display_name": "Childhood of Orhan Gazi",
            "seasons": [1]
        }
    ],
    "qualities": {
        "480p": ["480", "SD", "low", "480p"],
        "720p": ["720", "HD", "medium", "720p"],
        "1080p": ["1080", "FHD", "high", "1080p", "FullHD"]
    }
}

class BanglaSubtitleScanner:
    def __init__(self):
        self.setup_logging()
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })
        self.base_path = Path("playlists")
        self.base_path.mkdir(exist_ok=True)
        
    def setup_logging(self):
        log_path = Path("logs")
        log_path.mkdir(exist_ok=True)
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler(log_path / 'scanner.log'),
                logging.StreamHandler()
            ]
        )
        self.logger = logging.getLogger(__name__)
    
    def get_volume_links(self, series):
        """সব ভলিউম লিংক সংগ্রহ"""
        volumes = []
        try:
            resp = self.session.get(series['url'], timeout=30)
            soup = BeautifulSoup(resp.text, 'html.parser')
            
            patterns = [
                (r'/mehmed-fatih-sultan-volume-(\d+)/', 1),
                (r'/the-greatest-conquerors-v(\d+)/', 1),
                (r'/kurulus-orhan-season-(\d+)-volume-(\d+)/', 2),
                (r'/the-great-ruler-of-the-ottoman-empire-v(\d+)/', 1),
            ]
            
            for a in soup.find_all('a', href=True):
                href = a['href']
                for pattern, group_count in patterns:
                    match = re.search(pattern, href, re.I)
                    if match:
                        if group_count == 1:
                            vol_num = int(match.group(1))
                            season = 1
                        else:
                            season = int(match.group(1))
                            vol_num = int(match.group(2))
                        
                        volumes.append({
                            'number': vol_num,
                            'season': season,
                            'url': urljoin(series['url'], href),
                            'title': a.get_text(strip=True) or f"Volume {vol_num}"
                        })
            
            return sorted(volumes, key=lambda x: (x['season'], x['number']))
        except Exception as e:
            self.logger.error(f"Error getting volumes for {series['name']}: {e}")
            return []
    
    def extract_video_links(self, page_url):
        """পেজ থেকে ভিডিও লিংক বের করা"""
        videos = {'480p': None, '720p': None, '1080p': None}
        
        try:
            resp = self.session.get(page_url, timeout=30)
            html = resp.text
            
            # JSON-LD স্ক্রিপ্টে ভিডিও লিংক
            soup = BeautifulSoup(html, 'html.parser')
            for script in soup.find_all('script', type='application/ld+json'):
                if script.string:
                    try:
                        data = json.loads(script.string)
                        if isinstance(data, dict):
                            # ভিডিও ইউআরএল খোঁজা
                            for key in ['contentUrl', 'embedUrl', 'url']:
                                if key in data and isinstance(data[key], str):
                                    url = data[key]
                                    quality = self.detect_quality(url)
                                    if quality and not videos[quality]:
                                        videos[quality] = url
                    except:
                        pass
            
            # iframe থেকে লিংক
            for iframe in soup.find_all('iframe', src=True):
                src = iframe['src']
                if 'youtube.com' not in src and 'youtu.be' not in src:
                    quality = self.detect_quality(src)
                    if quality and not videos[quality]:
                        videos[quality] = src
            
            # সরাসরি ভিডিও ফাইল
            video_pattern = r'(https?://[^\s"\'<>]+\.(?:m3u8|mp4|ts)[^\s"\'<>]*)'
            all_videos = re.findall(video_pattern, html, re.I)
            
            for video_url in all_videos:
                quality = self.detect_quality(video_url)
                if quality and not videos[quality]:
                    videos[quality] = video_url
            
            return videos
        except Exception as e:
            self.logger.error(f"Error extracting video from {page_url}: {e}")
            return videos
    
    def detect_quality(self, url):
        """ভিডিও ইউআরএল থেকে কোয়ালিটি ডিটেক্ট"""
        url_lower = url.lower()
        for quality, patterns in CONFIG['qualities'].items():
            for pattern in patterns:
                if pattern.lower() in url_lower:
                    return quality
        return None
    
    def create_m3u_playlist(self, series_name, display_name, volumes, quality):
        """M3U প্লেলিস্ট তৈরি"""
        playlist_lines = ["#EXTM3U"]
        playlist_lines.append(f"#PLAYLIST: {display_name} - {quality.upper()}")
        playlist_lines.append(f"#UPDATED: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        playlist_lines.append(f"#SOURCE: GitHub Actions Auto Update")
        playlist_lines.append("")
        
        for vol in volumes:
            video_url = vol.get('video_links', {}).get(quality)
            if video_url:
                extinf = f"#EXTINF:-1 tvg-id=\"{series_name}\" tvg-name=\"{vol['title']}\" tvg-logo=\"\",{display_name} - Episode {vol['number']}"
                playlist_lines.append(extinf)
                playlist_lines.append(video_url)
                playlist_lines.append("")
        
        # সিরিজ ফোল্ডার তৈরি
        series_path = self.base_path / series_name
        series_path.mkdir(exist_ok=True)
        
        # সেভ করা
        playlist_file = series_path / f"{quality}.m3u"
        with open(playlist_file, 'w', encoding='utf-8') as f:
            f.write('\n'.join(playlist_lines))
        
        self.logger.info(f"✅ Created: {playlist_file} ({len([v for v in volumes if v.get('video_links', {}).get(quality)])} episodes)")
        return playlist_file
    
    def scan_all(self):
        """সব সিরিজ স্ক্যান"""
        results = {}
        
        for series in CONFIG['series']:
            self.logger.info(f"\n📺 Scanning: {series['display_name']}")
            
            # ভলিউম লিংক সংগ্রহ
            volumes = self.get_volume_links(series)
            self.logger.info(f"   Found {len(volumes)} volumes")
            
            # প্রতিটি ভলিউমের ভিডিও লিংক
            for vol in volumes:
                self.logger.info(f"   🔍 Processing {vol['title']}...")
                vol['video_links'] = self.extract_video_links(vol['url'])
                
                # রেট লিমিট এড়াতে
                import time
                time.sleep(1)
            
            # প্রতিটি কোয়ালিটির জন্য প্লেলিস্ট
            for quality in ['480p', '720p', '1080p']:
                self.create_m3u_playlist(
                    series['name'],
                    series['display_name'],
                    volumes,
                    quality
                )
            
            results[series['name']] = {
                'total_volumes': len(volumes),
                'qualities': {q: len([v for v in volumes if v.get('video_links', {}).get(q)]) for q in ['480p', '720p', '1080p']}
            }
        
        return results
    
    def create_readme(self):
        """README ফাইল তৈরি"""
        readme_content = """# 🎬 Bangla Subtitle M3U Playlists

## 📺 Available Series

"""
        for series in CONFIG['series']:
            readme_content += f"### {series['display_name']}\n"
            readme_content += f"- **480p**: `./playlists/{series['name']}/480p.m3u`\n"
            readme_content += f"- **720p**: `./playlists/{series['name']}/720p.m3u`\n"
            readme_content += f"- **1080p**: `./playlists/{series['name']}/1080p.m3u`\n\n"
        
        readme_content += f"""
## 📅 Last Updated
{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} UTC

## 🔧 How to Use
1. Download the playlist files
2. Open with any M3U-compatible player (VLC, Kodi, IPTV app)
3. Or use the raw GitHub URL

## 📱 Stream URLs
