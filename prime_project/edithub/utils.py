import re
import requests
from django.conf import settings
from typing import Optional, Dict
import logging

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
    Fetch TikTok channel data
    Note: TikTok doesn't have an official public API, so we'll use web scraping
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
    
    try:
        # TikTok profile URL
        profile_url = f'https://www.tiktok.com/@{username}'
        
        # Use a simple request to get the page
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        
        response = requests.get(profile_url, headers=headers, timeout=10)
        response.raise_for_status()
        
        # Parse the page for follower count (this is a simplified approach)
        # TikTok pages have JSON data embedded in the HTML
        html_content = response.text
        
        # Try to find follower count in the page
        # This is a basic implementation - in production, you might want to use
        # a more robust scraping solution or a third-party API
        follower_match = re.search(r'"followerCount":(\d+)', html_content)
        if follower_match:
            result['follower_count'] = int(follower_match.group(1))
        
        # Try to find channel name
        name_match = re.search(r'"nickname":"([^"]+)"', html_content)
        if name_match:
            result['channel_name'] = name_match.group(1)
        
        # Try to find avatar
        avatar_match = re.search(r'"avatarMedium":"([^"]+)"', html_content)
        if avatar_match:
            result['thumbnail'] = avatar_match.group(1).replace('\\u002F', '/')
        
        if not result['channel_name'] and not result['follower_count']:
            result['error'] = 'Could not extract channel data from TikTok page'
            # As a fallback, set the username as channel name
            result['channel_name'] = username
        
    except requests.exceptions.RequestException as e:
        logger.error(f"TikTok fetch error: {str(e)}")
        result['error'] = f'Failed to fetch channel data: {str(e)}'
        # Fallback: use username as channel name
        result['channel_name'] = username
    except Exception as e:
        logger.error(f"Unexpected error fetching TikTok data: {str(e)}")
        result['error'] = f'Unexpected error: {str(e)}'
        result['channel_name'] = username
    
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

