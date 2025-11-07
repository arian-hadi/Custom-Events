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
    """Fetch TikTok oEmbed metadata (thumbnail, author) for a video URL."""
    result: Dict[str, Optional[str]] = {
        'thumbnail_url': None,
        'author_name': None,
        'author_url': None,
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
        result['html'] = data.get('html')
        return result
    except Exception as e:
        logger.warning("TikTok oEmbed failed: %s", e)
        result['error'] = str(e)
        return result


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
        
        # Get channel subscriber count
        channel_id = video['snippet'].get('channelId')
        if channel_id:
            channel_data = fetch_youtube_channel_data(f"https://www.youtube.com/channel/{channel_id}")
            result['subscriber_count'] = channel_data.get('subscriber_count', 0)
        
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