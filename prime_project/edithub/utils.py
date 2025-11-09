import re
import requests
from django.conf import settings
from typing import Optional, Dict
import logging
import json

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
        
        # For handles/usernames (including @2.0Transformers format), use search API
        # This is more reliable for handles with special characters
        search_url = 'https://www.googleapis.com/youtube/v3/search'
        handle_name = channel_id.lstrip('@')
        
        # Search for the exact handle/channel name
        # Use the handle as the query, but also try to match exact channel handle
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
                
                # Check if handle is in customUrl
                handle_in_url = (
                    custom_url and handle_name.lower() in custom_url.lower()
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
                    
                    # Verify this is the correct channel
                    if full_custom_url:
                        expected_handle = f'@{handle_name}'.lower()
                        actual_handle = full_custom_url.lower()
                        if expected_handle == actual_handle or handle_name.lower() in actual_handle:
                            result['channel_name'] = channel['snippet']['title']
                            result['subscriber_count'] = int(channel['statistics'].get('subscriberCount', 0))
                            result['thumbnail'] = channel['snippet']['thumbnails'].get('high', {}).get('url', '')
                            return result
                        else:
                            logger.warning(f"Handle mismatch: expected '{expected_handle}', got '{actual_handle}'")
                    else:
                        # No customUrl, but we matched by title, so use it
                        result['channel_name'] = channel['snippet']['title']
                        result['subscriber_count'] = int(channel['statistics'].get('subscriberCount', 0))
                        result['thumbnail'] = channel['snippet']['thumbnails'].get('high', {}).get('url', '')
                        return result
            
            # If no good match found, try first non-Topic result
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
            patterns = [
                r'"nickname"\s*:\s*"([^"]+)"',
                r'"nickname":"([^"]+)"',
                r'"displayName"\s*:\s*"([^"]+)"',
                r'nickname["\']?\s*:\s*"([^"]+)"',
            ]
            for pattern in patterns:
                match = re.search(pattern, html_content)
                if match:
                    result['channel_name'] = match.group(1)
                    logger.info(f"Extracted channel name via regex: {result['channel_name']}")
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
                        
                        // Try DOM elements
                        try {
                            if (!data.nickname) {
                                const h1 = document.querySelector('h1[data-e2e="user-title"], h1');
                                if (h1) data.nickname = h1.textContent.trim();
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
    
    # Ensure we have at least username
    if not result['channel_name']:
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
                    for pattern in video_url_patterns:
                        matches = re.finditer(pattern, page_content)
                        for match in matches:
                            potential_url = match.group(1) if match.groups() else match.group(0)
                            # Clean up the URL
                            potential_url = potential_url.replace('\\u002F', '/').replace('\\/', '/')
                            # Validate it's a real video URL
                            if '.mp4' in potential_url or 'tiktokcdn.com' in potential_url:
                                video_src = potential_url
                                break
                        if video_src:
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
                    
                    result['video_url'] = video_src
                    logger.info(f"Successfully extracted TikTok video URL")
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
    Fetch TikTok video statistics (views, likes, comments, follower count)
    Note: TikTok doesn't have a public API, so this uses web scraping or third-party APIs
    Returns: {'views': int, 'likes': int, 'comments': int, 'follower_count': int, 'error': str}
    """
    result = {
        'views': 0,
        'likes': 0,
        'comments': 0,
        'follower_count': 0,
        'error': None
    }
    
    # TikTok doesn't have a public API, so we'll need to use web scraping
    # For now, return an error indicating this needs to be implemented
    # You can use libraries like playwright or selenium, or third-party APIs
    result['error'] = 'TikTok stats fetching not yet implemented. Requires web scraping or third-party API.'
    logger.warning("TikTok video stats fetching not implemented")
    
    # TODO: Implement TikTok stats fetching using web scraping or third-party API
    # Example approach:
    # 1. Use playwright/selenium to load the TikTok page
    # 2. Extract stats from the page HTML
    # 3. Or use a third-party API service
    
    return result


def calculate_youtube_points(views: int, likes: int, comments: int, subscriber_count: int) -> float:
    """
    Calculate YouTube ranking points based on the formula:
    Score = (Views × 0.4) + (Likes × 0.3) + (Comments × 0.2) + (Engagement Rate × 0.1)
    Engagement Rate = ((Likes + Comments) / Views) × 100
    All values are normalized by subscriber count for fairness.
    """
    if subscriber_count == 0:
        subscriber_count = 1  # Avoid division by zero
    
    # Normalize values by subscriber count
    normalized_views = views / subscriber_count if subscriber_count > 0 else 0
    normalized_likes = likes / subscriber_count if subscriber_count > 0 else 0
    normalized_comments = comments / subscriber_count if subscriber_count > 0 else 0
    
    # Calculate engagement rate
    if views > 0:
        engagement_rate = ((likes + comments) / views) * 100
    else:
        engagement_rate = 0
    
    # Calculate points
    points = (
        (normalized_views * 0.4) +
        (normalized_likes * 0.3) +
        (normalized_comments * 0.2) +
        (engagement_rate * 0.1)
    )
    
    return round(points, 2)


def calculate_tiktok_points(views: int, likes: int, comments: int, follower_count: int) -> float:
    """
    Calculate TikTok ranking points based on the formula:
    Score = (Views × 0.35) + (Likes × 0.4) + (Comments × 0.15) + (Engagement Rate × 0.1)
    Engagement Rate = ((Likes + Comments) / Views) × 100
    Values are normalized by follower count.
    """
    if follower_count == 0:
        follower_count = 1  # Avoid division by zero
    
    # Normalize values by follower count
    normalized_views = views / follower_count if follower_count > 0 else 0
    normalized_likes = likes / follower_count if follower_count > 0 else 0
    normalized_comments = comments / follower_count if follower_count > 0 else 0
    
    # Calculate engagement rate
    if views > 0:
        engagement_rate = ((likes + comments) / views) * 100
    else:
        engagement_rate = 0
    
    # Calculate points
    points = (
        (normalized_views * 0.35) +
        (normalized_likes * 0.4) +
        (normalized_comments * 0.15) +
        (engagement_rate * 0.1)
    )
    
    return round(points, 2)