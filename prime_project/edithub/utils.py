import re
import requests
from django.conf import settings
from typing import Optional, Dict, Tuple
import logging
import json
import math
from datetime import datetime, timedelta, timezone
from django.core.files.base import ContentFile
from django.core.files.images import ImageFile
from io import BytesIO
from PIL import Image

logger = logging.getLogger(__name__)


def extract_youtube_channel_id(url: str) -> Optional[str]:
    """Extract YouTube channel ID or username from URL"""
    patterns = [
        r'youtube\.com/channel/([a-zA-Z0-9_-]+)',  # Channel ID format: UC...
        r'youtube\.com/c/([a-zA-Z0-9_.-]+)',  # Custom URL - can include dots
        r'youtube\.com/user/([a-zA-Z0-9_.-]+)',  # User URL - can include dots
        r'youtube\.com/@([a-zA-Z0-9_.-]+)',  # Handle format - can include dots (e.g., @2.0Transformers)
        r'youtu\.be/([a-zA-Z0-9_-]+)',  # Video link, but might be used
    ]
    
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    return None


def extract_tiktok_username(url: str) -> Optional[str]:
    """Extract TikTok username from URL"""
    patterns = [
        r'tiktok\.com/@([a-zA-Z0-9_.]+)',
        r'vm\.tiktok\.com/([a-zA-Z0-9]+)',
    ]
    
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    return None


def fetch_youtube_channel_data(channel_url: str) -> Dict[str, any]:
    """
    Fetch YouTube channel data using YouTube Data API v3
    Returns: {'channel_name': str, 'subscriber_count': int, 'thumbnail': str, 'error': str}
    """
    result = {
        'channel_name': '',
        'subscriber_count': 0,
        'thumbnail': '',
        'error': None
    }
    
    # Get YouTube API key from settings
    api_key = getattr(settings, 'YOUTUBE_API_KEY', None)
    if not api_key:
        result['error'] = 'YouTube API key not configured'
        logger.warning("YouTube API key not configured")
        return result
    
    channel_id = extract_youtube_channel_id(channel_url)
    if not channel_id:
        result['error'] = 'Invalid YouTube URL format. Please use a channel URL like: https://www.youtube.com/@channelname or https://www.youtube.com/channel/CHANNEL_ID'
        return result
    
    try:
        api_url = 'https://www.googleapis.com/youtube/v3/channels'
        
        # Check if it's a channel ID (starts with UC) or a handle/username
        is_channel_id = channel_id.startswith('UC') and len(channel_id) > 10
        
        if is_channel_id:
            # Direct channel ID lookup
            params = {
                'part': 'snippet,statistics',
                'id': channel_id,
                'key': api_key
            }
            response = requests.get(api_url, params=params, timeout=10)
            
            # Handle 403 errors
            if response.status_code == 403:
                error_data = response.json()
                error_reason = error_data.get('error', {}).get('errors', [{}])[0].get('reason', '')
                if error_reason == 'quotaExceeded':
                    result['error'] = 'YouTube API quota exceeded'
                elif error_reason == 'keyInvalid':
                    result['error'] = 'Invalid YouTube API key'
                else:
                    result['error'] = f'API access forbidden. Check API key restrictions. Reason: {error_reason}'
                return result
            
            response.raise_for_status()
            data = response.json()
            
            if data.get('items'):
                channel = data['items'][0]
                result['channel_name'] = channel['snippet']['title']
                result['subscriber_count'] = int(channel['statistics'].get('subscriberCount', 0))
                result['thumbnail'] = channel['snippet']['thumbnails'].get('high', {}).get('url', '')
                return result
        
        # For handles/usernames, try direct lookup first (most efficient - 1 API call, 1 quota unit)
        handle_name = channel_id.lstrip('@')
        
        # Try direct handle lookup using forHandle parameter (standard YouTube API method)
        # This is the most efficient method: 1 API call vs 2 API calls with search API
        try:
            direct_params = {
                'part': 'snippet,statistics',
                'forHandle': handle_name,
                'key': api_key
            }
            direct_response = requests.get(api_url, params=direct_params, timeout=10)
            
            # If successful (200), we got the channel directly
            if direct_response.status_code == 200:
                direct_data = direct_response.json()
                if direct_data.get('items'):
                    channel = direct_data['items'][0]
                    # Verify the customUrl matches exactly (safety check)
                    full_custom_url = channel.get('snippet', {}).get('customUrl', '')
                    expected_handle = f'@{handle_name}'.lower()
                    actual_handle = full_custom_url.lower() if full_custom_url else ''
                    
                    # Exact match check - if forHandle worked, this should match
                    if actual_handle == expected_handle or actual_handle == handle_name.lower():
                        result['channel_name'] = channel['snippet']['title']
                        result['subscriber_count'] = int(channel['statistics'].get('subscriberCount', 0))
                        result['thumbnail'] = channel['snippet']['thumbnails'].get('high', {}).get('url', '')
                        logger.info(f"Successfully fetched channel via forHandle: {handle_name} (1 API call)")
                        return result
                    else:
                        # forHandle returned a channel but customUrl doesn't match - fall through to search
                        logger.warning(f"forHandle returned channel but customUrl mismatch: expected '{expected_handle}' or '{handle_name.lower()}', got '{actual_handle}'")
        except Exception as e:
            # If forHandle fails (API error, not supported, etc.), fall back to search
            logger.debug(f"forHandle lookup failed, using search API fallback: {str(e)}")
        
        # Fall back to search API method (only if forHandle didn't work)
        # This costs 100 quota units, so we only use it when necessary
        search_url = 'https://www.googleapis.com/youtube/v3/search'
        
        search_params = {
            'part': 'snippet',
            'q': handle_name,
            'type': 'channel',
            'key': api_key,
            'maxResults': 10  # Get more results to find exact match
        }
        
        search_response = requests.get(search_url, params=search_params, timeout=10)
        
        # Handle 403 errors
        if search_response.status_code == 403:
            error_data = search_response.json()
            error_reason = error_data.get('error', {}).get('errors', [{}])[0].get('reason', '')
            if error_reason == 'quotaExceeded':
                result['error'] = 'YouTube API quota exceeded'
            elif error_reason == 'keyInvalid':
                result['error'] = 'Invalid YouTube API key'
            else:
                result['error'] = f'API access forbidden. Check API key restrictions. Reason: {error_reason}'
            return result
        
        search_response.raise_for_status()
        search_data = search_response.json()
        
        # Find the exact channel match by checking customUrl or comparing handle
        # Filter out Topic channels and prioritize exact matches
        if search_data.get('items'):
            best_match = None
            exact_match = None
            
            for item in search_data['items']:
                channel_item = item.get('snippet', {})
                custom_url = channel_item.get('customUrl', '')
                channel_title = channel_item.get('title', '')
                channel_id_from_search = item['id']['channelId']
                
                # Skip Topic channels (auto-generated YouTube channels)
                # Topic channels typically have "Topic" in the title or description
                is_topic_channel = (
                    'Topic' in channel_title or
                    'topic' in channel_item.get('description', '').lower() or
                    channel_id_from_search.startswith('UC') and len(channel_id_from_search) > 20  # Topic channels have longer IDs
                )
                
                if is_topic_channel:
                    continue
                
                # Check for exact handle match
                # Handle format: @username (e.g., @2.0Transformers)
                handle_with_at = f'@{handle_name}'
                exact_handle_match = (
                    custom_url and custom_url.lower() == handle_with_at.lower()
                ) or (
                    # Sometimes customUrl doesn't include @, so check both
                    custom_url and custom_url.lower() == handle_name.lower()
                )
                
                # Check for title match (case-insensitive)
                title_match = channel_title.lower() == handle_name.lower()
                
                # Check if handle is in customUrl (stricter: require handle at start/end, not just anywhere)
                handle_in_url = False
                if custom_url:
                    custom_url_lower = custom_url.lower().lstrip('@')
                    handle_lower = handle_name.lower()
                    # Check if handle is at the start or exact match (more strict than just "in")
                    handle_in_url = (
                        custom_url_lower == handle_lower or
                        custom_url_lower == f'@{handle_lower}' or
                        custom_url_lower.startswith(handle_lower + '/') or
                        custom_url_lower.startswith(handle_lower + '_') or
                        custom_url_lower.startswith(handle_lower + '-')
                    )
                
                if exact_handle_match or (title_match and handle_in_url):
                    exact_match = item
                    break  # Found exact match, use this one
                elif handle_in_url or title_match:
                    # Good match but not exact
                    if not best_match:
                        best_match = item
            
            # Use exact match if found, otherwise use best match
            selected_item = exact_match or best_match
            
            if selected_item:
                channel_id_from_search = selected_item['id']['channelId']
                # Get full channel details
                params = {
                    'part': 'snippet,statistics',
                    'id': channel_id_from_search,
                    'key': api_key
                }
                response = requests.get(api_url, params=params, timeout=10)
                response.raise_for_status()
                data = response.json()
                
                if data.get('items'):
                    channel = data['items'][0]
                    # Double-check the customUrl from the full channel data
                    full_custom_url = channel.get('snippet', {}).get('customUrl', '')
                    
                    # Stricter verification - require exact match or handle at boundary
                    if full_custom_url:
                        expected_handle = f'@{handle_name}'.lower()
                        actual_handle = full_custom_url.lower()
                        handle_lower = handle_name.lower()
                        
                        # Exact match or handle at start (more strict than "in")
                        is_valid_match = (
                            actual_handle == expected_handle or
                            actual_handle == handle_lower or
                            actual_handle.startswith(handle_lower + '/') or
                            actual_handle.startswith(handle_lower + '_') or
                            actual_handle.startswith(handle_lower + '-') or
                            actual_handle == f'@{handle_lower}'
                        )
                        
                        if is_valid_match:
                            result['channel_name'] = channel['snippet']['title']
                            result['subscriber_count'] = int(channel['statistics'].get('subscriberCount', 0))
                            result['thumbnail'] = channel['snippet']['thumbnails'].get('high', {}).get('url', '')
                            logger.info(f"Successfully matched channel via search API: {handle_name} -> {full_custom_url}")
                            return result
                        else:
                            logger.warning(f"Handle mismatch after verification: expected '{expected_handle}' or '{handle_lower}', got '{actual_handle}'")
                            # Don't return here - continue to check other matches or fallback
                    else:
                        # No customUrl - only use if we had exact title match
                        if exact_match and title_match:
                            result['channel_name'] = channel['snippet']['title']
                            result['subscriber_count'] = int(channel['statistics'].get('subscriberCount', 0))
                            result['thumbnail'] = channel['snippet']['thumbnails'].get('high', {}).get('url', '')
                            logger.info(f"Matched channel by title (no customUrl): {handle_name}")
                            return result
            
            # Fallback: try first non-Topic result only if no matches found above
            if not exact_match and not best_match:
                for item in search_data['items']:
                    channel_title = item.get('snippet', {}).get('title', '')
                    if 'Topic' not in channel_title:
                        channel_id_from_search = item['id']['channelId']
                        params = {
                            'part': 'snippet,statistics',
                            'id': channel_id_from_search,
                            'key': api_key
                        }
                        response = requests.get(api_url, params=params, timeout=10)
                        response.raise_for_status()
                        data = response.json()
                        
                        if data.get('items'):
                            channel = data['items'][0]
                            result['channel_name'] = channel['snippet']['title']
                            result['subscriber_count'] = int(channel['statistics'].get('subscriberCount', 0))
                            result['thumbnail'] = channel['snippet']['thumbnails'].get('high', {}).get('url', '')
                            logger.warning(f"Using fallback result for handle '{handle_name}': {channel['snippet']['title']}")
                            return result
        
        result['error'] = f'Channel "{handle_name}" not found. Please verify the channel URL is correct.'
        
    except requests.exceptions.RequestException as e:
        logger.error(f"YouTube API error: {str(e)}")
        result['error'] = f'Failed to fetch channel data: {str(e)}'
    except Exception as e:
        logger.error(f"Unexpected error fetching YouTube data: {str(e)}")
        result['error'] = f'Unexpected error: {str(e)}'
    
    return result


def fetch_tiktok_channel_data(channel_url: str) -> Dict[str, any]:
    """
    Fetch TikTok channel data using Playwright for robust scraping
    TikTok requires JavaScript execution to load data, so simple HTTP requests don't work
    Returns: {'channel_name': str, 'follower_count': int, 'thumbnail': str, 'error': str}
    """
    result = {
        'channel_name': '',
        'follower_count': 0,
        'thumbnail': '',
        'error': None
    }
    
    username = extract_tiktok_username(channel_url)
    if not username:
        result['error'] = 'Invalid TikTok URL format'
        return result
    
    # Try simple request first (faster if it works)
    # TikTok often embeds data in initial HTML, so this might work without Playwright
    try:
        profile_url = f'https://www.tiktok.com/@{username}'
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.9',
            'Accept-Encoding': 'gzip, deflate, br',
            'DNT': '1',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
            'Referer': 'https://www.tiktok.com/',
        }
        
        response = requests.get(profile_url, headers=headers, timeout=20)
        response.raise_for_status()
        html_content = response.text
        
        # Try to extract JSON from script tags (TikTok embeds data here)
        json_data = None
        script_patterns = [
            r'<script[^>]*id="__UNIVERSAL_DATA_FOR_REHYDRATION__"[^>]*>(.*?)</script>',
            r'<script[^>]*type="application/json"[^>]*id="__UNIVERSAL_DATA_FOR_REHYDRATION__"[^>]*>(.*?)</script>',
            r'window\.__UNIVERSAL_DATA_FOR_REHYDRATION__\s*=\s*({.*?});',
        ]
        
        for pattern in script_patterns:
            script_match = re.search(pattern, html_content, re.DOTALL)
            if script_match:
                try:
                    json_str = script_match.group(1).strip().strip(';').strip()
                    # Clean up JSON string - remove any trailing semicolons or comments
                    json_str = re.sub(r';\s*$', '', json_str)
                    json_data = json.loads(json_str)
                    logger.info(f"Successfully parsed TikTok JSON data for: {username}")
                    break
                except (json.JSONDecodeError, IndexError) as e:
                    logger.debug(f"JSON parse failed for pattern {pattern[:50]}: {str(e)}")
                    continue
        
        # Extract from JSON if found
        if json_data:
            def find_user_data(obj, depth=0):
                if depth > 6:
                    return None
                if not isinstance(obj, dict):
                    return None
                # Check if this looks like user data
                if 'followerCount' in obj and ('nickname' in obj or 'displayName' in obj or 'name' in obj):
                    return obj
                # Search recursively
                for key, value in obj.items():
                    if isinstance(value, (dict, list)):
                        found = find_user_data(value, depth + 1)
                        if found:
                            return found
                return None
            
            user_data = find_user_data(json_data)
            if user_data:
                result['follower_count'] = int(user_data.get('followerCount', 0) or user_data.get('follower', 0))
                result['channel_name'] = (user_data.get('nickname') or 
                                         user_data.get('displayName') or 
                                         user_data.get('name') or 
                                         '')
                avatar = (user_data.get('avatarMedium') or 
                         user_data.get('avatarLarger') or 
                         user_data.get('avatar') or 
                         '')
                if avatar:
                    thumb = avatar.replace('\\u002F', '/').replace('\\/', '/')
                    if thumb.startswith('//'):
                        thumb = 'https:' + thumb
                    elif not thumb.startswith('http'):
                        thumb = 'https://' + thumb.lstrip('/')
                    result['thumbnail'] = thumb
                logger.info(f"Extracted from JSON: name={result['channel_name']}, followers={result['follower_count']}, thumb={'yes' if result['thumbnail'] else 'no'}")
        
        # Fallback to regex if JSON extraction didn't work or didn't find everything
        if not result['follower_count']:
            patterns = [
                r'"followerCount"\s*:\s*(\d+)',
                r'"followerCount":\s*(\d+)',
                r'"followerCount":(\d+)',
                r'followerCount["\']?\s*:\s*(\d+)',
            ]
            for pattern in patterns:
                match = re.search(pattern, html_content)
                if match:
                    try:
                        result['follower_count'] = int(match.group(1))
                        logger.info(f"Extracted follower count via regex: {result['follower_count']}")
                        break
                    except (ValueError, IndexError):
                        continue
        
        if not result['channel_name']:
            # Try to extract display name (nickname) - the styled name with custom fonts
            # This is different from the unique username
            patterns = [
                r'"nickname"\s*:\s*"([^"]+)"',
                r'"nickname":"([^"]+)"',
                r'"displayName"\s*:\s*"([^"]+)"',
                r'"uniqueId"\s*:\s*"([^"]+)"',  # This is the unique username, we want to avoid this
                r'nickname["\']?\s*:\s*"([^"]+)"',
                r'<h1[^>]*data-e2e="user-title"[^>]*>([^<]+)</h1>',
                r'<h1[^>]*>([^<]+)</h1>',  # Last resort - any h1
            ]
            for pattern in patterns:
                match = re.search(pattern, html_content)
                if match:
                    extracted_name = match.group(1)
                    # Make sure we're not getting the unique username instead of display name
                    # Display names can have spaces, emojis, special chars - usernames usually don't
                    if extracted_name and extracted_name != username:
                        result['channel_name'] = extracted_name
                        logger.info(f"Extracted display name via regex: {result['channel_name']}")
                        break
        
        if not result['thumbnail']:
            patterns = [
                r'"avatarMedium"\s*:\s*"([^"]+)"',
                r'"avatarLarger"\s*:\s*"([^"]+)"',
                r'"avatar"\s*:\s*"([^"]+)"',
                r'avatarMedium["\']?\s*:\s*"([^"]+)"',
            ]
            for pattern in patterns:
                match = re.search(pattern, html_content)
                if match:
                    thumb = match.group(1).replace('\\u002F', '/').replace('\\/', '/')
                    if thumb.startswith('//'):
                        thumb = 'https:' + thumb
                    elif not thumb.startswith('http'):
                        thumb = 'https://' + thumb.lstrip('/')
                    result['thumbnail'] = thumb
                    logger.info(f"Extracted thumbnail via regex")
                    break
        
        # If we got at least channel name and some data, return (don't require all fields)
        if result['channel_name']:
            logger.info(f"Simple request extracted data for {username}: name={result['channel_name']}, followers={result['follower_count']}, thumbnail={'yes' if result['thumbnail'] else 'no'}")
            return result
        
    except requests.exceptions.RequestException as e:
        logger.warning(f"TikTok simple fetch failed: {str(e)}, trying Playwright")
    except Exception as e:
        logger.warning(f"TikTok simple fetch error: {str(e)}, trying Playwright")
    
    # Use Playwright if simple request didn't work (TikTok requires JS execution)
    try:
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            result['error'] = 'Playwright is not installed. Run: pip install playwright && playwright install chromium'
            result['channel_name'] = username
            logger.error("Playwright not installed for TikTok channel data")
            return result
        
        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=True,
                args=['--no-sandbox', '--disable-setuid-sandbox', '--disable-blink-features=AutomationControlled']
            )
            
            context = browser.new_context(
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                viewport={'width': 1920, 'height': 1080}
            )
            
            context.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined});")
            
            page = context.new_page()
            
            try:
                profile_url = f'https://www.tiktok.com/@{username}'
                logger.info(f"Loading TikTok profile with Playwright: {profile_url}")
                
                # Use 'load' instead of 'networkidle' - TikTok pages have continuous network activity
                # Also increase timeout and add retry logic
                try:
                    page.goto(profile_url, wait_until='load', timeout=45000)
                except Exception as goto_error:
                    # If load times out, try domcontentloaded (faster, less strict)
                    logger.warning(f"Load timeout, trying domcontentloaded: {str(goto_error)}")
                    try:
                        page.goto(profile_url, wait_until='domcontentloaded', timeout=20000)
                    except Exception:
                        # If that also fails, just continue - page might still have data
                        logger.warning("Both load and domcontentloaded timed out, continuing anyway")
                
                # Wait for dynamic content to load
                page.wait_for_timeout(3000)
                
                # Try to wait for key elements that indicate page loaded
                try:
                    page.wait_for_selector('h1, [data-e2e="user-title"], body', timeout=5000)
                except Exception:
                    pass  # Continue even if selectors not found
                
                # Extract data using JavaScript (safe version that avoids browser objects)
                js_code = """
                    () => {
                        const data = {};
                        const username = """ + json.dumps(username) + """;
                        
                        // Helper to safely check if a value is a plain object
                        function isPlainObject(obj) {
                            if (!obj || typeof obj !== 'object') return false;
                            if (obj.constructor && obj.constructor.name !== 'Object') return false;
                            // Avoid browser objects like CSSStyleSheet, NodeList, etc.
                            if (obj.nodeType !== undefined) return false;
                            if (obj.length !== undefined && typeof obj.length === 'number' && !Array.isArray(obj)) return false;
                            try {
                                return Object.getPrototypeOf(obj) === Object.prototype || Object.getPrototypeOf(obj) === null;
                            } catch(e) {
                                return false;
                            }
                        }
                        
                        // Try window.__UNIVERSAL_DATA_FOR_REHYDRATION__
                        if (window.__UNIVERSAL_DATA_FOR_REHYDRATION__) {
                            const ud = window.__UNIVERSAL_DATA_FOR_REHYDRATION__;
                            function findUser(obj, depth=0) {
                                if (depth > 8) return null;
                                if (!isPlainObject(obj) && !Array.isArray(obj)) return null;
                                
                                // Check if this object has user data
                                if (isPlainObject(obj)) {
                                    if (obj.followerCount !== undefined && (obj.nickname || obj.displayName)) {
                                        return obj;
                                    }
                                }
                                
                                // Safely iterate
                                try {
                                    if (Array.isArray(obj)) {
                                        for (let i = 0; i < Math.min(obj.length, 100); i++) {
                                            const found = findUser(obj[i], depth+1);
                                            if (found) return found;
                                        }
                                    } else if (isPlainObject(obj)) {
                                        const keys = Object.keys(obj);
                                        for (let i = 0; i < Math.min(keys.length, 200); i++) {
                                            const key = keys[i];
                                            try {
                                                const value = obj[key];
                                                // Skip functions and browser objects
                                                if (typeof value === 'function') continue;
                                                if (value && typeof value === 'object' && value.nodeType !== undefined) continue;
                                                const found = findUser(value, depth+1);
                                                if (found) return found;
                                            } catch(e) {
                                                continue; // Skip if we can't access this property
                                            }
                                        }
                                    }
                                } catch(e) {
                                    // Ignore errors when accessing properties
                                }
                                return null;
                            }
                            
                            try {
                                const user = findUser(ud);
                                if (user && isPlainObject(user)) {
                                    data.followerCount = user.followerCount || user.follower;
                                    data.nickname = user.nickname || user.displayName || user.name;
                                    data.avatar = user.avatarMedium || user.avatarLarger || user.avatar;
                                }
                            } catch(e) {
                                // Ignore errors
                            }
                        }
                        
                        // Try DOM elements - prioritize display name (the styled name with custom fonts)
                        try {
                            if (!data.nickname) {
                                // Try multiple selectors for the display name (styled name)
                                const selectors = [
                                    'h1[data-e2e="user-title"]',
                                    'h1[data-e2e="user-subtitle"]',
                                    'h1.epjbyn1',
                                    'h1[class*="user-title"]',
                                    'h1[class*="user-subtitle"]',
                                    'h1',
                                    '[data-e2e="user-title"]',
                                    '.user-title',
                                    'h2[data-e2e="user-title"]',
                                ];
                                
                                for (const selector of selectors) {
                                    const el = document.querySelector(selector);
                                    if (el) {
                                        const text = el.textContent.trim();
                                        // Make sure it's not the unique username (which usually doesn't have special characters)
                                        // Display names can have emojis, special characters, etc.
                                        if (text && text !== username) {
                                            data.nickname = text;
                                            break;
                                        }
                                    }
                                }
                                
                                // If still not found, try to find the main heading that's not the username
                                if (!data.nickname) {
                                    const headings = document.querySelectorAll('h1, h2');
                                    for (const h of headings) {
                                        const text = h.textContent.trim();
                                        if (text && text !== username && text.length > 0) {
                                            data.nickname = text;
                                            break;
                                        }
                                    }
                                }
                            }
                            
                            if (!data.followerCount) {
                                const followerEl = document.querySelector('[data-e2e="followers-count"]');
                                if (followerEl) {
                                    const text = followerEl.textContent.trim();
                                    const match = text.match(/([\\d.]+)([KMB]?)/i);
                                    if (match) {
                                        let count = parseFloat(match[1]);
                                        if (match[2] === 'K') count *= 1000;
                                        else if (match[2] === 'M') count *= 1000000;
                                        else if (match[2] === 'B') count *= 1000000000;
                                        data.followerCount = Math.floor(count);
                                    }
                                }
                            }
                            
                            if (!data.avatar) {
                                const img = document.querySelector('[data-e2e="user-avatar"] img, img[src*="avatar"]');
                                if (img) data.avatar = img.src || img.getAttribute('src');
                            }
                        } catch(e) {
                            // Ignore DOM access errors
                        }
                        
                        return data;
                    }
                """
                user_data = page.evaluate(js_code)
                
                if user_data:
                    if user_data.get('followerCount'):
                        result['follower_count'] = int(user_data['followerCount'])
                    if user_data.get('nickname'):
                        result['channel_name'] = user_data['nickname']
                    if user_data.get('avatar'):
                        thumb = user_data['avatar']
                        if thumb.startswith('//'):
                            thumb = 'https:' + thumb
                        elif not thumb.startswith('http'):
                            thumb = 'https://' + thumb.lstrip('/')
                        result['thumbnail'] = thumb
                
                # Fallback to page content parsing
                if not result['follower_count'] or not result['thumbnail']:
                    page_content = page.content()
                    if not result['follower_count']:
                        match = re.search(r'"followerCount"\s*:\s*(\d+)', page_content)
                        if match:
                            result['follower_count'] = int(match.group(1))
                    if not result['thumbnail']:
                        match = re.search(r'"avatarMedium"\s*:\s*"([^"]+)"', page_content)
                        if match:
                            result['thumbnail'] = match.group(1).replace('\\u002F', '/')
                
            except Exception as e:
                error_msg = str(e)
                logger.error(f"Playwright error: {error_msg}", exc_info=True)
                
                # Even if page load failed, try to extract data from whatever is available
                try:
                    page_content = page.content()
                    # Try regex extraction as last resort
                    if not result['follower_count']:
                        match = re.search(r'"followerCount"\s*:\s*(\d+)', page_content)
                        if match:
                            result['follower_count'] = int(match.group(1))
                    if not result['channel_name']:
                        match = re.search(r'"nickname"\s*:\s*"([^"]+)"', page_content)
                        if match:
                            result['channel_name'] = match.group(1)
                    if not result['thumbnail']:
                        match = re.search(r'"avatarMedium"\s*:\s*"([^"]+)"', page_content)
                        if match:
                            result['thumbnail'] = match.group(1).replace('\\u002F', '/')
                except Exception:
                    pass
                
                # Try additional DOM extraction if we still don't have the display name
                if not result['channel_name']:
                    try:
                        # Wait a bit for page to fully render
                        page.wait_for_timeout(2000)
                        
                        # Try to get display name from various DOM selectors
                        display_name_selectors = [
                            'h1[data-e2e="user-title"]',
                            'h1[data-e2e="user-subtitle"]',
                            'h1',
                            '[data-e2e="user-title"]',
                        ]
                        
                        for selector in display_name_selectors:
                            try:
                                element = page.query_selector(selector)
                                if element:
                                    text = element.inner_text().strip()
                                    if text and text != username:
                                        result['channel_name'] = text
                                        logger.info(f"Extracted display name from DOM selector '{selector}': {result['channel_name']}")
                                        break
                            except Exception:
                                continue
                    except Exception as e:
                        logger.debug(f"Additional DOM extraction failed: {str(e)}")
                
                # Only set error if we got nothing
                if not result['channel_name'] and not result['follower_count']:
                    result['error'] = f'Error loading TikTok profile: {error_msg}'
            finally:
                try:
                    browser.close()
                except Exception:
                    pass
                
    except Exception as e:
        logger.error(f"Playwright setup error: {str(e)}", exc_info=True)
        result['error'] = f'Playwright error: {str(e)}'
    
    # Only use username as last resort - prefer to leave empty if we can't get display name
    # This way the user knows we couldn't fetch the display name
    if not result['channel_name']:
        logger.warning(f"Could not extract display name for TikTok user {username}, using username as fallback")
        result['channel_name'] = username
    
    logger.info(f"TikTok extraction result for {username}: name={result['channel_name']}, followers={result['follower_count']}, thumbnail={'yes' if result['thumbnail'] else 'no'}")
    
    return result


def validate_channel_url(url: str):
    """
    Validate if URL is a YouTube or TikTok channel URL
    Returns: (is_valid, channel_type, error_message)
    """
    if not url:
        return False, None, 'URL is required'
    
    url_lower = url.lower()
    
    # Check for YouTube
    if 'youtube.com' in url_lower or 'youtu.be' in url_lower:
        channel_id = extract_youtube_channel_id(url)
        if channel_id:
            return True, 'youtube', None
        return False, None, 'Invalid YouTube URL format. Please use a channel URL (not video URL)'
    
    # Check for TikTok
    if 'tiktok.com' in url_lower:
        username = extract_tiktok_username(url)
        if username:
            return True, 'tiktok', None
        return False, None, 'Invalid TikTok URL format'
    
    return False, None, 'URL must be a YouTube or TikTok channel link'


def get_youtube_channel_id_from_link(channel_link: str) -> Optional[str]:
    """Get the actual YouTube channel ID from a channel link (handles both handles and channel IDs)"""
    channel_id_or_handle = extract_youtube_channel_id(channel_link)
    if not channel_id_or_handle:
        return None
    
    # If it's already a channel ID (starts with UC and is long enough), return it
    if channel_id_or_handle.startswith('UC') and len(channel_id_or_handle) >= 20:
        return channel_id_or_handle
    
    # It's a handle, need to resolve it
    api_key = getattr(settings, 'YOUTUBE_API_KEY', None)
    if not api_key:
        return None
    
    try:
        # Use search API to find channel
        search_url = 'https://www.googleapis.com/youtube/v3/search'
        handle_name = channel_id_or_handle.lstrip('@')
        search_params = {
            'part': 'snippet',
            'q': handle_name,
            'type': 'channel',
            'key': api_key,
            'maxResults': 10
        }
        search_response = requests.get(search_url, params=search_params, timeout=10)
        search_response.raise_for_status()
        search_data = search_response.json()
        
        if search_data.get('items'):
            # Find exact match by customUrl
            for item in search_data['items']:
                channel_id = item['id']['channelId']
                custom_url = item['snippet'].get('customUrl', '')
                if custom_url and handle_name.lower() in custom_url.lower().lstrip('@'):
                    return channel_id
            # If no exact match, return first non-topic channel
            for item in search_data['items']:
                if 'Topic' not in item['snippet'].get('title', ''):
                    return item['id']['channelId']
    except Exception as e:
        logger.error(f"Error getting channel ID from link: {str(e)}")
    
    return None


def extract_youtube_channel_from_video(video_url: str) -> Optional[str]:
    """Extract YouTube channel ID or handle from a video URL"""
    if not video_url:
        return None
    
    # Extract video ID first
    video_id = None
    patterns = [
        r'youtube\.com/watch\?v=([a-zA-Z0-9_-]+)',
        r'youtube\.com/shorts/([a-zA-Z0-9_-]+)',
        r'youtu\.be/([a-zA-Z0-9_-]+)',
        r'youtube\.com/embed/([a-zA-Z0-9_-]+)',
    ]
    
    for pattern in patterns:
        match = re.search(pattern, video_url)
        if match:
            video_id = match.group(1)
            break
    
    if not video_id:
        return None
    
    # Use YouTube API to get channel ID from video
    api_key = getattr(settings, 'YOUTUBE_API_KEY', None)
    if not api_key:
        return None
    
    try:
        api_url = 'https://www.googleapis.com/youtube/v3/videos'
        params = {
            'part': 'snippet',
            'id': video_id,
            'key': api_key
        }
        response = requests.get(api_url, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()
        
        if data.get('items'):
            channel_id = data['items'][0]['snippet']['channelId']
            return channel_id
    except Exception as e:
        logger.error(f"Error extracting channel from video: {str(e)}")
    
    return None


def extract_tiktok_username_from_video(video_url: str) -> Optional[str]:
    """Extract TikTok username from a video URL"""
    if not video_url:
        return None
    
    # TikTok video URLs are like: https://www.tiktok.com/@username/video/1234567890
    patterns = [
        r'tiktok\.com/@([a-zA-Z0-9_.]+)/video',
        r'tiktok\.com/@([a-zA-Z0-9_.]+)',
    ]
    
    for pattern in patterns:
        match = re.search(pattern, video_url)
        if match:
            return match.group(1)
    
    return None


def extract_tiktok_video_url(video_url: str) -> Dict[str, Optional[str]]:
    """
    Extract direct video file URL from TikTok using Playwright web scraping.
    This allows us to display TikTok videos as clean HTML5 video players (like YouTube)
    instead of using TikTok's embed which shows likes/comments/share buttons.
    
    Returns: {'video_url': str, 'username': str, 'error': str}
    """
    result = {
        'video_url': None,
        'username': None,
        'error': None
    }
    
    if not video_url:
        result['error'] = 'Video URL is required'
        return result
    
    # Extract username from URL first
    username = extract_tiktok_username_from_video(video_url)
    if username:
        result['username'] = username
    
    try:
        # Import playwright (with fallback if not installed)
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            result['error'] = 'Playwright is not installed. Run: pip install playwright && playwright install chromium'
            logger.error("Playwright not installed")
            return result
        
        with sync_playwright() as p:
            # Launch browser in headless mode with stealth settings
            browser = p.chromium.launch(
                headless=True,
                args=[
                    '--no-sandbox',
                    '--disable-setuid-sandbox',
                    '--disable-blink-features=AutomationControlled',  # Hide automation
                    '--disable-dev-shm-usage',
                    '--disable-web-security',
                    '--disable-features=IsolateOrigins,site-per-process',
                ]
            )
            
            # Create context with realistic settings to avoid detection
            context = browser.new_context(
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                viewport={'width': 1920, 'height': 1080},
                locale='en-US',
                timezone_id='America/New_York',
                permissions=['geolocation'],
                geolocation={'latitude': 40.7128, 'longitude': -74.0060},  # New York
                color_scheme='light',
                # Add extra headers to look more like a real browser
                extra_http_headers={
                    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
                    'Accept-Language': 'en-US,en;q=0.9',
                    'Accept-Encoding': 'gzip, deflate, br',
                    'DNT': '1',
                    'Connection': 'keep-alive',
                    'Upgrade-Insecure-Requests': '1',
                    'Sec-Fetch-Dest': 'document',
                    'Sec-Fetch-Mode': 'navigate',
                    'Sec-Fetch-Site': 'none',
                    'Sec-Fetch-User': '?1',
                    'Cache-Control': 'max-age=0',
                }
            )
            
            # Add JavaScript to hide webdriver property
            context.add_init_script("""
                Object.defineProperty(navigator, 'webdriver', {
                    get: () => undefined
                });
                
                // Override plugins to look more realistic
                Object.defineProperty(navigator, 'plugins', {
                    get: () => [1, 2, 3, 4, 5]
                });
                
                // Override languages
                Object.defineProperty(navigator, 'languages', {
                    get: () => ['en-US', 'en']
                });
                
                // Mock chrome object
                window.chrome = {
                    runtime: {}
                };
            """)
            
            page = context.new_page()
            
            try:
                # Navigate to TikTok video page with stealth approach
                logger.info(f"Loading TikTok video page: {video_url}")
                
                # First, try to load the page
                try:
                    # Use load state instead of networkidle to avoid waiting too long
                    page.goto(video_url, wait_until='load', timeout=20000)
                    # Wait a bit for dynamic content
                    page.wait_for_timeout(3000)
                except Exception as e:
                    result['error'] = f'Timeout loading TikTok page: {str(e)}'
                    logger.warning(f"Timeout loading TikTok page: {video_url}")
                    return result
                
                # Check if we got blocked or redirected
                current_url = page.url
                if 'challenge' in current_url.lower() or 'verify' in current_url.lower():
                    result['error'] = 'TikTok detected automation and blocked access'
                    logger.warning(f"TikTok blocked access for: {video_url}")
                    return result
                
                # Wait for video element to load with multiple attempts
                video_found = False
                for attempt in range(3):
                    try:
                        page.wait_for_selector('video', timeout=5000)
                        video_found = True
                        break
                    except Exception:
                        # Scroll down a bit to trigger lazy loading
                        page.evaluate('window.scrollBy(0, 300)')
                        page.wait_for_timeout(1000)
                
                if not video_found:
                    # Final check if video exists
                    if not page.query_selector('video'):
                        result['error'] = 'Video element not found on TikTok page (may require login or be blocked)'
                        logger.warning(f"Video element not found on TikTok page: {video_url}")
                        return result
                
                # Try multiple methods to get video URL
                video_src = None
                
                # Method 1: Direct video element src
                video_element = page.query_selector('video')
                if video_element:
                    video_src = video_element.get_attribute('src')
                    if not video_src:
                        # Method 2: Check source tag inside video
                        source_element = page.query_selector('video source')
                        if source_element:
                            video_src = source_element.get_attribute('src')
                
                # Method 3: Extract from network requests (if video element doesn't have src)
                if not video_src:
                    # Wait for video to start loading
                    page.wait_for_timeout(1000)
                    # Try to get video URL from page's video element after it loads
                    video_src = page.evaluate("""
                        () => {
                            const video = document.querySelector('video');
                            if (video) {
                                return video.src || video.currentSrc || (video.querySelector('source')?.src);
                            }
                            return null;
                        }
                    """)
                
                # Method 4: Try to extract from page source/JSON data
                if not video_src:
                    # TikTok sometimes embeds video URL in JSON data
                    page_content = page.content()
                    # Look for video URLs in the page source with more patterns
                    video_url_patterns = [
                        r'"downloadAddr":"([^"]+)"',
                        r'"playAddr":"([^"]+)"',
                        r'"videoUrl":"([^"]+)"',
                        r'"playUrl":"([^"]+)"',
                        r'"video":\s*\{[^}]*"downloadAddr":\s*"([^"]+)"',
                        r'https://[^"]*\.tiktokcdn\.com/[^"]*\.mp4[^"]*',
                        r'https://[^"]*\.tiktokcdn\.com/[^"]*\.mp4\?[^"]*',
                        r'https://[^"]*v\.tiktokcdn\.com/[^"]*',
                    ]
                    found_urls = []
                    for pattern in video_url_patterns:
                        matches = re.finditer(pattern, page_content)
                        for match in matches:
                            potential_url = match.group(1) if match.groups() else match.group(0)
                            # Clean up the URL
                            potential_url = potential_url.replace('\\u002F', '/').replace('\\/', '/')
                            # Validate it's a real URL
                            if '.mp4' in potential_url or 'tiktokcdn.com' in potential_url:
                                found_urls.append(potential_url)
                    
                    # Filter: Prefer video URLs over audio URLs
                    # TikTok audio URLs often have mime_type=audio_mpeg in the URL
                    for url in found_urls:
                        # Skip audio URLs
                        if 'mime_type=audio' in url or 'audio_mpeg' in url or 'mime_type=audio_mpeg' in url:
                            continue
                        # Prefer video URLs with mime_type=video_mp4
                        if 'mime_type=video_mp4' in url or 'mime_type=video' in url:
                            video_src = url
                            break
                        # Fallback: any URL that's not audio
                        if not video_src:
                            video_src = url
                            break
                
                # Method 5: Try to intercept network requests for video
                if not video_src:
                    try:
                        # Wait for any video network requests
                        page.wait_for_timeout(2000)
                        # Try to get video from network response
                        video_src = page.evaluate("""
                            () => {
                                // Try to find video in any script tags with JSON data
                                const scripts = document.querySelectorAll('script');
                                for (let script of scripts) {
                                    const content = script.textContent || '';
                                    const match = content.match(/https:\\/\\/[^"']*\\.tiktokcdn\\.com[^"']*\\.mp4[^"']*/);
                                    if (match) {
                                        return match[0].replace(/\\\\/g, '/');
                                    }
                                }
                                return null;
                            }
                        """)
                    except Exception:
                        pass
                
                if video_src:
                    # Clean up the URL
                    if video_src.startswith('//'):
                        video_src = 'https:' + video_src
                    elif not video_src.startswith('http'):
                        video_src = 'https://' + video_src.lstrip('/')
                    
                    # Final check: Make sure it's not an audio URL
                    if 'mime_type=audio' in video_src or 'audio_mpeg' in video_src:
                        logger.warning(f"Extracted URL appears to be audio, not video: {video_src[:100]}...")
                        video_src = None  # Reject audio URLs
                    
                    if video_src:
                        result['video_url'] = video_src
                        logger.info(f"Successfully extracted TikTok video URL (verified as video, not audio)")
                    else:
                        result['error'] = 'Only audio URL found, video URL not available'
                        logger.warning("Only audio URL was found, skipping")
                else:
                    result['error'] = 'Could not extract video URL from TikTok page'
                    logger.warning(f"Could not find video URL in TikTok page: {video_url}")
                
            except Exception as e:
                result['error'] = f'Error loading TikTok page: {str(e)}'
                logger.error(f"Error extracting TikTok video URL: {str(e)}")
            finally:
                browser.close()
                
    except Exception as e:
        result['error'] = f'Playwright error: {str(e)}'
        logger.error(f"Playwright error extracting TikTok video: {str(e)}")
    
    return result


def verify_video_belongs_to_channel(video_url: str, channel_link: str, channel_type: str) -> tuple[bool, str]:
    """
    Verify that a video URL belongs to the same channel as the channel_link
    Returns: (is_valid, error_message)
    """
    if channel_type == 'youtube':
        api_key = getattr(settings, 'YOUTUBE_API_KEY', None)
        if not api_key:
            return False, 'YouTube API not configured'
        
        try:
            # Extract video ID
            video_id_match = re.search(r'(?:youtube\.com/(?:watch\?v=|shorts/)|youtu\.be/)([a-zA-Z0-9_-]+)', video_url)
            if not video_id_match:
                return False, 'Invalid YouTube video URL format'
            
            video_id = video_id_match.group(1)
            
            # Get channel ID from video
            video_api_url = 'https://www.googleapis.com/youtube/v3/videos'
            video_params = {
                'part': 'snippet',
                'id': video_id,
                'key': api_key
            }
            video_response = requests.get(video_api_url, params=video_params, timeout=10)
            video_response.raise_for_status()
            video_data = video_response.json()
            
            if not video_data.get('items'):
                return False, 'Video not found'
            
            video_channel_id = video_data['items'][0]['snippet']['channelId']
            video_channel_custom_url = video_data['items'][0]['snippet'].get('customUrl', '')
            
            # Get actual channel ID from channel_link (handles both handles and channel IDs)
            approved_channel_id = get_youtube_channel_id_from_link(channel_link)
            if not approved_channel_id:
                # Fallback: try comparing customUrls/handles
                channel_id_or_handle = extract_youtube_channel_id(channel_link)
                if channel_id_or_handle and video_channel_custom_url:
                    expected_handle = channel_id_or_handle.lower().lstrip('@')
                    actual_handle = video_channel_custom_url.lower().lstrip('@')
                    if expected_handle == actual_handle or expected_handle in actual_handle:
                        return True, ''
                return False, 'Invalid channel link format or could not resolve channel ID'
            
            # Compare channel IDs
            if video_channel_id == approved_channel_id:
                return True, ''
            else:
                return False, 'Video does not belong to your approved channel'
            
        except Exception as e:
            logger.error(f"Error verifying YouTube video: {str(e)}")
            return False, f'Error verifying video: {str(e)}'
    
    elif channel_type == 'tiktok':
        # Extract username from video
        video_username = extract_tiktok_username_from_video(video_url)
        if not video_username:
            return False, 'Could not extract username from video URL'
        
        # Extract username from channel_link
        channel_username = extract_tiktok_username(channel_link)
        if not channel_username:
            return False, 'Invalid channel link format'
        
        # Compare usernames (case-insensitive)
        if video_username.lower() == channel_username.lower():
            return True, ''
        else:
            return False, 'Video does not belong to your approved channel'
    
    return False, 'Unsupported channel type'


def extract_youtube_video_id(url: str) -> Optional[str]:
    """Extract YouTube video ID from common URL formats."""
    if not url:
        return None
    patterns = [
        r"youtube\.com/shorts/([\w-]{11})",
        r"[?&]v=([\w-]{11})",
        r"youtu\.be/([\w-]{11})",
        r"youtube\.com/embed/([\w-]{11})",
    ]
    for pattern in patterns:
        m = re.search(pattern, url)
        if m:
            return m.group(1)
    return None


def youtube_thumbnail_from_url(url: str) -> Optional[str]:
    vid = extract_youtube_video_id(url)
    if not vid:
        return None
    return f"https://img.youtube.com/vi/{vid}/maxresdefault.jpg"


def fetch_tiktok_oembed(video_url: str) -> Dict[str, Optional[str]]:
    """Fetch TikTok oEmbed metadata (thumbnail, author, title) for a video URL."""
    result: Dict[str, Optional[str]] = {
        'thumbnail_url': None,
        'author_name': None,
        'author_url': None,
        'title': None,
        'html': None,
        'error': None,
    }
    if not video_url:
        result['error'] = 'Missing video URL'
        return result
    try:
        endpoint = 'https://www.tiktok.com/oembed'
        resp = requests.get(endpoint, params={'url': video_url}, timeout=8)
        resp.raise_for_status()
        data = resp.json()
        result['thumbnail_url'] = data.get('thumbnail_url')
        result['author_name'] = data.get('author_name')
        result['author_url'] = data.get('author_url')
        result['title'] = data.get('title')  # TikTok oEmbed includes title
        result['html'] = data.get('html')
        return result
    except Exception as e:
        logger.warning("TikTok oEmbed failed: %s", e)
        result['error'] = str(e)
        return result


def is_valid_thumbnail_url(thumbnail_url: str) -> bool:
    """
    Check if a thumbnail URL is valid and not a placeholder/empty value.
    
    Args:
        thumbnail_url: The thumbnail URL to validate
        
    Returns:
        True if the URL is valid, False otherwise
    """
    if not thumbnail_url:
        return False
    
    # Convert to string and strip whitespace
    url = str(thumbnail_url).strip()
    
    # Check for empty strings
    if not url:
        return False
    
    # List of invalid/placeholder values to check for
    invalid_patterns = [
        'no-image',
        'no-image.jpg',
        'no-image.png',
        'no-thumbnail',
        'no-thumbnail.jpg',
        'no-thumbnail.png',
        'placeholder',
        'placeholder.jpg',
        'placeholder.png',
        'default',
        'default.jpg',
        'default.png',
        'none',
        'null',
        'undefined',
        'missing',
        'missing.jpg',
        'missing.png',
    ]
    
    # Check if URL contains any invalid patterns (case-insensitive)
    url_lower = url.lower()
    for pattern in invalid_patterns:
        if pattern in url_lower:
            return False
    
    # Check if it's a valid URL format (starts with http:// or https://)
    if not (url.startswith('http://') or url.startswith('https://')):
        return False
    
    # Additional check: if URL is too short, it's likely invalid
    if len(url) < 10:
        return False
    
    return True


def get_fallback_thumbnail(existing_thumbnail: str, new_thumbnail: str, *additional_fallbacks: str) -> str:
    """
    Get the best available thumbnail from multiple options, preferring existing valid ones.
    
    Args:
        existing_thumbnail: The current/existing thumbnail URL
        new_thumbnail: The new thumbnail URL to potentially use
        *additional_fallbacks: Additional thumbnail URLs to check as fallbacks
        
    Returns:
        The best valid thumbnail URL, or empty string if none are valid
    """
    # First, prefer existing thumbnail if it's valid
    if is_valid_thumbnail_url(existing_thumbnail):
        return existing_thumbnail.strip()
    
    # Then check new thumbnail
    if is_valid_thumbnail_url(new_thumbnail):
        return new_thumbnail.strip()
    
    # Finally check additional fallbacks
    for fallback in additional_fallbacks:
        if is_valid_thumbnail_url(fallback):
            return fallback.strip()
    
    # Return empty string if no valid thumbnail found
    return ''


def download_image_from_url(image_url: str) -> Optional[ContentFile]:
    """
    Download an image from a URL and return it as a Django ContentFile.
    
    Args:
        image_url: URL of the image to download
        
    Returns:
        ContentFile object with the image data, or None if download fails
    """
    if not image_url or not is_valid_thumbnail_url(image_url):
        return None
    
    try:
        # Download the image
        response = requests.get(image_url, timeout=10, stream=True)
        response.raise_for_status()
        
        # Check content type
        content_type = response.headers.get('content-type', '')
        if not content_type.startswith('image/'):
            logger.warning(f"URL {image_url} does not return an image (content-type: {content_type})")
            return None
        
        # Read image data
        image_data = BytesIO(response.content)
        
        # Verify it's a valid image by opening with PIL
        try:
            img = Image.open(image_data)
            img.verify()  # Verify it's a valid image
        except Exception as e:
            logger.warning(f"Invalid image data from {image_url}: {e}")
            return None
        
        # Reset BytesIO position after verify
        image_data.seek(0)
        
        # Get file extension from URL or content type
        ext = 'jpg'  # default
        if '.jpg' in image_url.lower() or '.jpeg' in image_url.lower():
            ext = 'jpg'
        elif '.png' in image_url.lower():
            ext = 'png'
        elif '.gif' in image_url.lower():
            ext = 'gif'
        elif '.webp' in image_url.lower():
            ext = 'webp'
        elif 'png' in content_type.lower():
            ext = 'png'
        elif 'gif' in content_type.lower():
            ext = 'gif'
        elif 'webp' in content_type.lower():
            ext = 'webp'
        
        # Create filename
        filename = f"profile_picture_{datetime.now().strftime('%Y%m%d_%H%M%S')}.{ext}"
        
        # Create ContentFile
        return ContentFile(image_data.read(), name=filename)
        
    except requests.RequestException as e:
        logger.error(f"Error downloading image from {image_url}: {e}")
        return None
    except Exception as e:
        logger.error(f"Unexpected error downloading image from {image_url}: {e}")
        return None


def fetch_tiktok_video_title(video_url: str) -> Optional[str]:
    """
    Fetch TikTok video title using oEmbed API (simplest method)
    Returns: title string or None if not found
    """
    try:
        oembed_data = fetch_tiktok_oembed(video_url)
        if oembed_data.get('title') and not oembed_data.get('error'):
            return oembed_data['title']
    except Exception as e:
        logger.warning(f"Failed to fetch TikTok video title: {str(e)}")
    return None


def fetch_youtube_video_stats(video_url: str) -> Dict[str, any]:
    """
    Fetch YouTube video statistics (views, likes, comments) using YouTube Data API v3
    Returns: {'views': int, 'likes': int, 'comments': int, 'subscriber_count': int, 'error': str}
    """
    result = {
        'views': 0,
        'likes': 0,
        'comments': 0,
        'subscriber_count': 0,
        'error': None
    }
    
    api_key = getattr(settings, 'YOUTUBE_API_KEY', None)
    if not api_key:
        result['error'] = 'YouTube API key not configured'
        return result
    
    video_id = extract_youtube_video_id(video_url)
    if not video_id:
        result['error'] = 'Could not extract video ID from URL'
        return result
    
    try:
        # Get video statistics
        api_url = 'https://www.googleapis.com/youtube/v3/videos'
        params = {
            'part': 'statistics,snippet',
            'id': video_id,
            'key': api_key
        }
        response = requests.get(api_url, params=params, timeout=10)
        
        if response.status_code == 403:
            error_data = response.json()
            error_reason = error_data.get('error', {}).get('errors', [{}])[0].get('reason', '')
            result['error'] = f'API access forbidden: {error_reason}'
            return result
        
        response.raise_for_status()
        data = response.json()
        
        if not data.get('items'):
            result['error'] = 'Video not found'
            return result
        
        video = data['items'][0]
        stats = video.get('statistics', {})
        
        result['views'] = int(stats.get('viewCount', 0))
        result['likes'] = int(stats.get('likeCount', 0))
        result['comments'] = int(stats.get('commentCount', 0))
        
        # OPTIMIZATION: Skip subscriber_count fetch - it's now reused from EditorApplication
        # This reduces API calls by 50% as subscriber_count is fetched once when user applies
        # and reused for all their video submissions
        # result['subscriber_count'] is set to 0 but won't be used (we use EditorApplication.follower_count instead)
        result['subscriber_count'] = 0
        
        return result
        
    except Exception as e:
        logger.error(f"Error fetching YouTube video stats: {str(e)}")
        result['error'] = str(e)
        return result


def fetch_tiktok_video_stats(video_url: str) -> Dict[str, any]:
    """
    Fetch TikTok video statistics using web scraping (similar to fetch_tiktok_channel_data)
    TikTok requires JavaScript execution to load data, so we use Playwright
    Returns: {'views': int, 'likes': int, 'comments': int, 'follower_count': int, 'error': str}
    """
    result = {
        'views': 0,
        'likes': 0,
        'comments': 0,
        'follower_count': 0,
        'error': None
    }
    
    if not video_url:
        result['error'] = 'Video URL is required'
        return result
    
    # Try simple HTTP request first (faster if it works)
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.9',
            'Accept-Encoding': 'gzip, deflate, br',
            'DNT': '1',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
            'Referer': 'https://www.tiktok.com/',
        }
        
        response = requests.get(video_url, headers=headers, timeout=20)
        response.raise_for_status()
        html_content = response.text
        
        # Try to extract JSON from script tags
        json_data = None
        script_patterns = [
            r'<script[^>]*id="__UNIVERSAL_DATA_FOR_REHYDRATION__"[^>]*>(.*?)</script>',
            r'<script[^>]*type="application/json"[^>]*id="__UNIVERSAL_DATA_FOR_REHYDRATION__"[^>]*>(.*?)</script>',
            r'window\.__UNIVERSAL_DATA_FOR_REHYDRATION__\s*=\s*({.*?});',
        ]
        
        for pattern in script_patterns:
            script_match = re.search(pattern, html_content, re.DOTALL)
            if script_match:
                try:
                    json_str = script_match.group(1).strip().strip(';').strip()
                    json_str = re.sub(r';\s*$', '', json_str)
                    json_data = json.loads(json_str)
                    logger.info("Successfully parsed TikTok video JSON data")
                    break
                except (json.JSONDecodeError, IndexError):
                    continue
        
        # Extract video stats from JSON
        if json_data:
            def find_video_data(obj, depth=0):
                if depth > 6:
                    return None
                if not isinstance(obj, dict):
                    return None
                # Check if this looks like video data
                if 'playCount' in obj or 'viewCount' in obj or 'diggCount' in obj or 'commentCount' in obj:
                    return obj
                # Search recursively
                for key, value in obj.items():
                    if isinstance(value, (dict, list)):
                        found = find_video_data(value, depth + 1)
                        if found:
                            return found
                return None
            
            video_data = find_video_data(json_data)
            if video_data:
                result['views'] = int(video_data.get('playCount', 0) or video_data.get('viewCount', 0) or 0)
                result['likes'] = int(video_data.get('diggCount', 0) or video_data.get('likeCount', 0) or 0)
                result['comments'] = int(video_data.get('commentCount', 0) or 0)
                logger.info(f"Extracted from JSON: views={result['views']}, likes={result['likes']}, comments={result['comments']}")
        
        # Fallback to regex if JSON extraction didn't work
        if not result['views']:
            patterns = [
                r'"playCount"\s*:\s*(\d+)',
                r'"viewCount"\s*:\s*(\d+)',
                r'"playCount":\s*(\d+)',
                r'playCount["\']?\s*:\s*(\d+)',
            ]
            for pattern in patterns:
                match = re.search(pattern, html_content)
                if match:
                    try:
                        result['views'] = int(match.group(1))
                        logger.info(f"Extracted views via regex: {result['views']}")
                        break
                    except (ValueError, IndexError):
                        continue
        
        if not result['likes']:
            patterns = [
                r'"diggCount"\s*:\s*(\d+)',
                r'"likeCount"\s*:\s*(\d+)',
                r'"diggCount":\s*(\d+)',
                r'diggCount["\']?\s*:\s*(\d+)',
            ]
            for pattern in patterns:
                match = re.search(pattern, html_content)
                if match:
                    try:
                        result['likes'] = int(match.group(1))
                        logger.info(f"Extracted likes via regex: {result['likes']}")
                        break
                    except (ValueError, IndexError):
                        continue
        
        if not result['comments']:
            patterns = [
                r'"commentCount"\s*:\s*(\d+)',
                r'"commentCount":\s*(\d+)',
                r'commentCount["\']?\s*:\s*(\d+)',
            ]
            for pattern in patterns:
                match = re.search(pattern, html_content)
                if match:
                    try:
                        result['comments'] = int(match.group(1))
                        logger.info(f"Extracted comments via regex: {result['comments']}")
                        break
                    except (ValueError, IndexError):
                        continue
        
        # If we got at least some stats, return (don't require all fields)
        if result['views'] or result['likes'] or result['comments']:
            logger.info(f"Simple request extracted stats: views={result['views']}, likes={result['likes']}, comments={result['comments']}")
            return result
        
    except requests.exceptions.RequestException as e:
        logger.warning(f"TikTok simple fetch failed: {str(e)}, trying Playwright")
    except Exception as e:
        logger.warning(f"TikTok simple fetch error: {str(e)}, trying Playwright")
    
    # Use Playwright if simple request didn't work
    try:
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            result['error'] = 'Playwright is not installed. Run: pip install playwright && playwright install chromium'
            logger.error("Playwright not installed for TikTok video stats")
            return result
        
        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=True,
                args=['--no-sandbox', '--disable-setuid-sandbox', '--disable-blink-features=AutomationControlled']
            )
            
            context = browser.new_context(
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                viewport={'width': 1920, 'height': 1080}
            )
            
            context.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined});")
            
            page = context.new_page()
            
            try:
                logger.info(f"Loading TikTok video page with Playwright: {video_url}")
                
                try:
                    page.goto(video_url, wait_until='load', timeout=45000)
                except Exception as goto_error:
                    logger.warning(f"Load timeout, trying domcontentloaded: {str(goto_error)}")
                    try:
                        page.goto(video_url, wait_until='domcontentloaded', timeout=20000)
                    except Exception:
                        logger.warning("Both load and domcontentloaded timed out, continuing anyway")
                
                # Wait for dynamic content to load
                page.wait_for_timeout(3000)
                
                # Try to wait for video stats elements
                try:
                    page.wait_for_selector('body', timeout=5000)
                except Exception:
                    pass
                
                # Extract stats using JavaScript
                js_code = """
                    () => {
                        const data = {};
                        
                        function isPlainObject(obj) {
                            if (!obj || typeof obj !== 'object') return false;
                            if (obj.constructor && obj.constructor.name !== 'Object') return false;
                            if (obj.nodeType !== undefined) return false;
                            if (obj.length !== undefined && typeof obj.length === 'number' && !Array.isArray(obj)) return false;
                            try {
                                return Object.getPrototypeOf(obj) === Object.prototype || Object.getPrototypeOf(obj) === null;
                            } catch(e) {
                                return false;
                            }
                        }
                        
                        // Try window.__UNIVERSAL_DATA_FOR_REHYDRATION__
                        if (window.__UNIVERSAL_DATA_FOR_REHYDRATION__) {
                            const ud = window.__UNIVERSAL_DATA_FOR_REHYDRATION__;
                            function findVideo(obj, depth=0) {
                                if (depth > 8) return null;
                                if (!isPlainObject(obj) && !Array.isArray(obj)) return null;
                                
                                if (isPlainObject(obj)) {
                                    if ((obj.playCount !== undefined || obj.viewCount !== undefined || obj.diggCount !== undefined) && 
                                        (obj.playCount !== undefined || obj.diggCount !== undefined || obj.commentCount !== undefined)) {
                                        return obj;
                                    }
                                }
                                
                                try {
                                    if (Array.isArray(obj)) {
                                        for (let i = 0; i < Math.min(obj.length, 100); i++) {
                                            const found = findVideo(obj[i], depth+1);
                                            if (found) return found;
                                        }
                                    } else if (isPlainObject(obj)) {
                                        const keys = Object.keys(obj);
                                        for (let i = 0; i < Math.min(keys.length, 200); i++) {
                                            const key = keys[i];
                                            try {
                                                const value = obj[key];
                                                if (typeof value === 'function') continue;
                                                if (value && typeof value === 'object' && value.nodeType !== undefined) continue;
                                                const found = findVideo(value, depth+1);
                                                if (found) return found;
                                            } catch(e) {
                                                continue;
                                            }
                                        }
                                    }
                                } catch(e) {
                                }
                                return null;
                            }
                            
                            try {
                                const video = findVideo(ud);
                                if (video && isPlainObject(video)) {
                                    data.views = video.playCount || video.viewCount || 0;
                                    data.likes = video.diggCount || video.likeCount || 0;
                                    data.comments = video.commentCount || 0;
                                }
                            } catch(e) {
                            }
                        }
                        
                        // Try DOM elements as fallback
                        try {
                            if (!data.views) {
                                const viewEl = document.querySelector('[data-e2e="video-views"], [class*="view"]');
                                if (viewEl) {
                                    const text = viewEl.textContent.trim();
                                    const match = text.match(/([\\d.]+)([KMB]?)/i);
                                    if (match) {
                                        let count = parseFloat(match[1]);
                                        if (match[2] === 'K') count *= 1000;
                                        else if (match[2] === 'M') count *= 1000000;
                                        else if (match[2] === 'B') count *= 1000000000;
                                        data.views = Math.floor(count);
                                    }
                                }
                            }
                            
                            if (!data.likes) {
                                const likeEl = document.querySelector('[data-e2e="like-count"], [class*="like"]');
                                if (likeEl) {
                                    const text = likeEl.textContent.trim();
                                    const match = text.match(/([\\d.]+)([KMB]?)/i);
                                    if (match) {
                                        let count = parseFloat(match[1]);
                                        if (match[2] === 'K') count *= 1000;
                                        else if (match[2] === 'M') count *= 1000000;
                                        else if (match[2] === 'B') count *= 1000000000;
                                        data.likes = Math.floor(count);
                                    }
                                }
                            }
                            
                            if (!data.comments) {
                                const commentEl = document.querySelector('[data-e2e="comment-count"], [class*="comment"]');
                                if (commentEl) {
                                    const text = commentEl.textContent.trim();
                                    const match = text.match(/([\\d.]+)([KMB]?)/i);
                                    if (match) {
                                        let count = parseFloat(match[1]);
                                        if (match[2] === 'K') count *= 1000;
                                        else if (match[2] === 'M') count *= 1000000;
                                        else if (match[2] === 'B') count *= 1000000000;
                                        data.comments = Math.floor(count);
                                    }
                                }
                            }
                        } catch(e) {
                        }
                        
                        return data;
                    }
                """
                video_data = page.evaluate(js_code)
                
                if video_data:
                    if video_data.get('views'):
                        result['views'] = int(video_data['views'])
                    if video_data.get('likes'):
                        result['likes'] = int(video_data['likes'])
                    if video_data.get('comments'):
                        result['comments'] = int(video_data['comments'])
                
                # Fallback to page content parsing
                if not result['views'] or not result['likes'] or not result['comments']:
                    page_content = page.content()
                    if not result['views']:
                        match = re.search(r'"playCount"\s*:\s*(\d+)|"viewCount"\s*:\s*(\d+)', page_content)
                        if match:
                            result['views'] = int(match.group(1) or match.group(2))
                    if not result['likes']:
                        match = re.search(r'"diggCount"\s*:\s*(\d+)|"likeCount"\s*:\s*(\d+)', page_content)
                        if match:
                            result['likes'] = int(match.group(1) or match.group(2))
                    if not result['comments']:
                        match = re.search(r'"commentCount"\s*:\s*(\d+)', page_content)
                        if match:
                            result['comments'] = int(match.group(1))
                
            except Exception as e:
                error_msg = str(e)
                logger.error(f"Playwright error: {error_msg}", exc_info=True)
                
                # Try to extract from page content even if page load failed
                try:
                    page_content = page.content()
                    if not result['views']:
                        match = re.search(r'"playCount"\s*:\s*(\d+)|"viewCount"\s*:\s*(\d+)', page_content)
                        if match:
                            result['views'] = int(match.group(1) or match.group(2))
                    if not result['likes']:
                        match = re.search(r'"diggCount"\s*:\s*(\d+)|"likeCount"\s*:\s*(\d+)', page_content)
                        if match:
                            result['likes'] = int(match.group(1) or match.group(2))
                    if not result['comments']:
                        match = re.search(r'"commentCount"\s*:\s*(\d+)', page_content)
                        if match:
                            result['comments'] = int(match.group(1))
                except Exception:
                    pass
                
                # Only set error if we got nothing
                if not result['views'] and not result['likes'] and not result['comments']:
                    result['error'] = f'Error loading TikTok video: {error_msg}'
            finally:
                try:
                    browser.close()
                except Exception:
                    pass
                
    except Exception as e:
        logger.error(f"Playwright setup error: {str(e)}", exc_info=True)
        if not result['views'] and not result['likes'] and not result['comments']:
            result['error'] = f'Playwright error: {str(e)}'
    
    # Note: follower_count is not available from video page
    # It should be fetched from channel data (already stored in EditorApplication)
    result['follower_count'] = 0
    
    logger.info(f"TikTok video stats extraction result: views={result['views']}, likes={result['likes']}, comments={result['comments']}, error={result['error']}")
    
    return result


def calculate_youtube_points(views: int, likes: int, comments: int, subscriber_count: int) -> float:
    """
    Calculate YouTube ranking points with fairness improvements for smaller creators:
    - Uses logarithmic scaling for subscriber count normalization
    - Caps subscriber count at 1M for normalization
    - Increased engagement rate weight (20% instead of 10%)
    - Engagement bonus multiplier for high engagement (>15%)
    - Minimum threshold protection for very small creators
    
    Formula: (Normalized Views × 0.35) + (Normalized Likes × 0.25) + (Normalized Comments × 0.2) + (Engagement Rate × 0.2)
    """
    if subscriber_count == 0:
        subscriber_count = 1  # Avoid division by zero
    
    # Cap subscriber count at 1M for normalization fairness
    capped_subscriber_count = min(subscriber_count, 1000000)
    
    # Use logarithmic scaling for normalization (more fair for smaller creators)
    # Add 1 to avoid log(0) and ensure minimum threshold protection
    log_subscriber = math.log10(max(capped_subscriber_count, 1) + 1)
    
    # Normalize values using logarithmic scaling
    # This helps smaller creators compete more fairly
    if log_subscriber > 0:
        normalized_views = views / log_subscriber if views > 0 else 0
        normalized_likes = likes / log_subscriber if likes > 0 else 0
        normalized_comments = comments / log_subscriber if comments > 0 else 0
    else:
        normalized_views = normalized_likes = normalized_comments = 0
    
    # Calculate engagement rate (percentage)
    if views > 0:
        engagement_rate = ((likes + comments) / views) * 100
    else:
        engagement_rate = 0
    
    # Base points calculation with increased engagement weight (20% instead of 10%)
    base_points = (
        (normalized_views * 0.35) +
        (normalized_likes * 0.25) +
        (normalized_comments * 0.2) +
        (engagement_rate * 0.2)  # Increased from 0.1 to 0.2
    )
    
    # Engagement bonus multiplier for high engagement (rewards quality over quantity)
    engagement_multiplier = 1.0
    if engagement_rate > 20:
        engagement_multiplier = 1.5  # 50% bonus for >20% engagement
    elif engagement_rate > 15:
        engagement_multiplier = 1.3  # 30% bonus for >15% engagement
    elif engagement_rate > 10:
        engagement_multiplier = 1.2  # 20% bonus for >10% engagement
    
    points = base_points * engagement_multiplier
    
    # Minimum threshold protection: ensure very small creators get meaningful points
    # If subscriber count < 1K and engagement is decent, add bonus
    if subscriber_count < 1000 and engagement_rate > 5:
        points += 5.0  # Small bonus for small creators with decent engagement
    
    return round(points, 2)


def calculate_tiktok_points(views: int, likes: int, comments: int, follower_count: int) -> float:
    """
    Calculate TikTok ranking points with fairness improvements for smaller creators:
    - Uses logarithmic scaling for follower count normalization
    - Caps follower count at 1M for normalization
    - Increased engagement rate weight (20% instead of 10%)
    - Engagement bonus multiplier for high engagement (>15%)
    - Minimum threshold protection for very small creators
    
    Formula: (Normalized Views × 0.3) + (Normalized Likes × 0.35) + (Normalized Comments × 0.15) + (Engagement Rate × 0.2)
    """
    if follower_count == 0:
        follower_count = 1  # Avoid division by zero
    
    # Cap follower count at 1M for normalization fairness
    capped_follower_count = min(follower_count, 1000000)
    
    # Use logarithmic scaling for normalization (more fair for smaller creators)
    # Add 1 to avoid log(0) and ensure minimum threshold protection
    log_follower = math.log10(max(capped_follower_count, 1) + 1)
    
    # Normalize values using logarithmic scaling
    # This helps smaller creators compete more fairly
    if log_follower > 0:
        normalized_views = views / log_follower if views > 0 else 0
        normalized_likes = likes / log_follower if likes > 0 else 0
        normalized_comments = comments / log_follower if comments > 0 else 0
    else:
        normalized_views = normalized_likes = normalized_comments = 0
    
    # Calculate engagement rate (percentage)
    if views > 0:
        engagement_rate = ((likes + comments) / views) * 100
    else:
        engagement_rate = 0
    
    # Base points calculation with increased engagement weight (20% instead of 10%)
    base_points = (
        (normalized_views * 0.3) +
        (normalized_likes * 0.35) +
        (normalized_comments * 0.15) +
        (engagement_rate * 0.2)  # Increased from 0.1 to 0.2
    )
    
    # Engagement bonus multiplier for high engagement (rewards quality over quantity)
    engagement_multiplier = 1.0
    if engagement_rate > 20:
        engagement_multiplier = 1.5  # 50% bonus for >20% engagement
    elif engagement_rate > 15:
        engagement_multiplier = 1.3  # 30% bonus for >15% engagement
    elif engagement_rate > 10:
        engagement_multiplier = 1.2  # 20% bonus for >10% engagement
    
    points = base_points * engagement_multiplier
    
    # Minimum threshold protection: ensure very small creators get meaningful points
    # If follower count < 1K and engagement is decent, add bonus
    if follower_count < 1000 and engagement_rate > 5:
        points += 5.0  # Small bonus for small creators with decent engagement
    
    return round(points, 2)


# Weekly Competition System Functions

def get_week_start_end(now: datetime = None) -> Tuple[datetime, datetime]:
    """
    Get the current competition week's start (Monday 00:00 UTC) and end (Sunday 23:59 UTC).
    This is the full display week (Mon-Sun).
    
    Args:
        now: Optional datetime to use as reference. Defaults to current time.
    
    Returns:
        Tuple of (week_start, week_end) as datetime objects
    """
    if now is None:
        now = datetime.now(timezone.utc)
    
    # Get Monday of current week (weekday 0 = Monday)
    days_since_monday = (now.weekday()) % 7
    week_start = (now - timedelta(days=days_since_monday)).replace(hour=0, minute=0, second=0, microsecond=0)
    
    # Get Sunday 23:59:59 of the same week (full week display)
    week_end = week_start + timedelta(days=6, hours=23, minutes=59, seconds=59)
    
    return week_start, week_end


def get_competition_end(now: datetime = None) -> datetime:
    """
    Get the competition end time (Friday 23:59 UTC).
    Points are only calculated/updated Monday-Friday.
    
    Args:
        now: Optional datetime to use as reference. Defaults to current time.
    
    Returns:
        Competition end datetime (Friday 23:59:59)
    """
    if now is None:
        now = datetime.now(timezone.utc)
    
    # Get Monday of current week
    days_since_monday = (now.weekday()) % 7
    week_start = (now - timedelta(days=days_since_monday)).replace(hour=0, minute=0, second=0, microsecond=0)
    
    # Get Friday 23:59:59 of the same week
    competition_end = week_start + timedelta(days=4, hours=23, minutes=59, seconds=59)
    
    return competition_end


def get_competition_state(now: datetime = None) -> Dict[str, any]:
    """
    Determine the current state of the weekly competition.
    
    Returns:
        Dict with:
        - 'state': 'live' (Mon-Fri, points updating) or 'results' (Sat-Sun, frozen rankings)
        - 'week_start': datetime of Monday 00:00 UTC
        - 'week_end': datetime of Sunday 23:59 UTC (full display week)
        - 'competition_end': datetime of Friday 23:59 UTC (when points stop updating)
        - 'time_remaining': timedelta until competition end (if live)
        - 'next_week_start': datetime of next Monday 00:00 UTC
    """
    if now is None:
        now = datetime.now(timezone.utc)
    
    week_start, week_end = get_week_start_end(now)  # Full week (Mon-Sun)
    competition_end = get_competition_end(now)  # Competition end (Fri)
    next_week_start = week_start + timedelta(days=7)
    
    # Check if we're in the competition period (Mon-Fri) or results period (Sat-Sun)
    if now <= competition_end:
        # Competition is live (Monday to Friday) - points are updating
        time_remaining = competition_end - now
        return {
            'state': 'live',
            'week_start': week_start,
            'week_end': week_end,  # Full week end (Sunday)
            'competition_end': competition_end,  # Competition end (Friday)
            'time_remaining': time_remaining,
            'next_week_start': next_week_start,
        }
    else:
        # Showing results (Saturday to Sunday) - rankings are frozen
        return {
            'state': 'results',
            'week_start': week_start,
            'week_end': week_end,  # Full week end (Sunday)
            'competition_end': competition_end,  # Competition end (Friday)
            'next_week_start': next_week_start,
            'time_until_next': next_week_start - now,
        }


def format_countdown(timedelta_obj: timedelta) -> str:
    """Format a timedelta object as a countdown string"""
    if timedelta_obj.total_seconds() < 0:
        return "00:00:00"
    
    total_seconds = int(timedelta_obj.total_seconds())
    hours = total_seconds // 3600
    minutes = (total_seconds % 3600) // 60
    seconds = total_seconds % 60
    
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}"


def check_user_achievements(user):
    """
    Check all achievement-based titles and unlock them if user qualifies.
    Returns list of newly unlocked titles.
    """
    from .models import EditorTitle, UserTitleUnlock, WeekWinner, EditSubmission
    from django.db.models import Sum, Avg, Max
    
    achievement_titles = EditorTitle.objects.filter(
        unlock_method__in=['achievement', 'both'],
        achievement_type__isnull=False,
        is_active=True
    )
    
    unlocked_titles = []
    
    for title in achievement_titles:
        # Skip if already unlocked
        if UserTitleUnlock.objects.filter(user=user, title=title).exists():
            continue
        
        qualifies = False
        
        try:
            if title.achievement_type == 'rank_1_wins':
                # Count only rank #1 (first place) wins - becoming Edit of the Week
                win_count = WeekWinner.objects.filter(user=user, week_rank=1).count()
                qualifies = win_count >= title.achievement_threshold
                
            elif title.achievement_type == 'rank_2_wins':
                # Count only rank #2 (second place) wins
                win_count = WeekWinner.objects.filter(user=user, week_rank=2).count()
                qualifies = win_count >= title.achievement_threshold
                
            elif title.achievement_type == 'rank_3_wins':
                # Count only rank #3 (third place) wins
                win_count = WeekWinner.objects.filter(user=user, week_rank=3).count()
                qualifies = win_count >= title.achievement_threshold
                
            elif title.achievement_type == 'total_points':
                # Sum of all calculated_points from verified submissions (overall total)
                total_points_result = EditSubmission.objects.filter(
                    user=user,
                    status='verified'
                ).aggregate(Sum('calculated_points'))['calculated_points__sum']
                
                # Handle None case and convert to float for comparison
                if total_points_result is None:
                    total_points = 0.0
                else:
                    total_points = float(total_points_result)
                
                qualifies = total_points >= float(title.achievement_threshold)
                
            elif title.achievement_type == 'points_per_edit':
                # Points for a single edit - check if user has at least one edit with this many points
                max_points = EditSubmission.objects.filter(
                    user=user,
                    status='verified'
                ).aggregate(Max('calculated_points'))['calculated_points__max'] or 0
                qualifies = float(max_points) >= title.achievement_threshold
                
            elif title.achievement_type == 'total_submissions':
                # Count total number of verified submissions
                submission_count = EditSubmission.objects.filter(
                    user=user,
                    status='verified'
                ).count()
                qualifies = submission_count >= title.achievement_threshold
                
            elif title.achievement_type == 'consecutive_weeks':
                # Get maximum consecutive weeks from all verified submissions
                max_consecutive_weeks = EditSubmission.objects.filter(
                    user=user,
                    status='verified'
                ).aggregate(Max('weeks_participated'))['weeks_participated__max'] or 0
                qualifies = max_consecutive_weeks >= title.achievement_threshold
            
            if qualifies:
                UserTitleUnlock.objects.get_or_create(
                    user=user,
                    title=title,
                    defaults={'unlock_method': 'achievement'}
                )
                unlocked_titles.append(title)
                logger.info(f"User {user.username} unlocked title '{title.name}' via achievement")
                
        except Exception as e:
            logger.error(f"Error checking achievement for title {title.name} and user {user.username}: {str(e)}")
            continue
    
    return unlocked_titles


def is_title_unlocked_for_user(user, title):
    """
    Check if a title is unlocked for a user.
    Returns True if unlocked, False otherwise.
    """
    from .models import UserTitleUnlock
    
    # Free titles are always unlocked (unless they're manual)
    if title.cost_coins == 0 and title.unlock_method == 'coins':
        return True
    
    # Manual titles can only be unlocked via UserTitleUnlock (admin grant)
    # Check if unlocked via achievement, coins, or manual
    return UserTitleUnlock.objects.filter(user=user, title=title).exists()


def get_user_achievement_progress(user, title):
    """
    Get the user's current progress towards unlocking an achievement-based title.
    Returns a dict with current_value, threshold, and progress_percentage.
    """
    from .models import WeekWinner, EditSubmission
    from django.db.models import Sum, Avg, Max
    
    if not title.achievement_type or title.unlock_method not in ['achievement', 'both']:
        return None
    
    current_value = 0
    threshold = title.achievement_threshold
    
    try:
        if title.achievement_type == 'rank_1_wins':
            # Count only rank #1 (first place) wins - becoming Edit of the Week
            current_value = WeekWinner.objects.filter(user=user, week_rank=1).count()
            
        elif title.achievement_type == 'rank_2_wins':
            # Count only rank #2 (second place) wins
            current_value = WeekWinner.objects.filter(user=user, week_rank=2).count()
            
        elif title.achievement_type == 'rank_3_wins':
            # Count only rank #3 (third place) wins
            current_value = WeekWinner.objects.filter(user=user, week_rank=3).count()
            
        elif title.achievement_type == 'total_points':
            # Sum of all calculated_points from verified submissions (overall total)
            total_points_result = EditSubmission.objects.filter(
                user=user,
                status='verified'
            ).aggregate(Sum('calculated_points'))['calculated_points__sum']
            
            # Handle None case and convert to float
            if total_points_result is None:
                current_value = 0.0
            else:
                current_value = float(total_points_result)
            
        elif title.achievement_type == 'points_per_edit':
            # Points for a single edit - get the maximum points from any single edit
            max_points = EditSubmission.objects.filter(
                user=user,
                status='verified'
            ).aggregate(Max('calculated_points'))['calculated_points__max'] or 0
            current_value = float(max_points)
            
        elif title.achievement_type == 'total_submissions':
            # Count total number of verified submissions
            current_value = EditSubmission.objects.filter(
                user=user,
                status='verified'
            ).count()
            
        elif title.achievement_type == 'consecutive_weeks':
            # Get maximum consecutive weeks from all verified submissions
            current_value = EditSubmission.objects.filter(
                user=user,
                status='verified'
            ).aggregate(Max('weeks_participated'))['weeks_participated__max'] or 0
        
        # Calculate progress percentage
        if threshold > 0:
            progress_percentage = min(100, (current_value / threshold) * 100)
        else:
            progress_percentage = 0
        
        return {
            'current_value': current_value,
            'threshold': threshold,
            'progress_percentage': round(progress_percentage, 1),
            'is_complete': current_value >= threshold
        }
        
    except Exception as e:
        logger.error(f"Error calculating progress for title {title.name} and user {user.username}: {str(e)}")
        return None