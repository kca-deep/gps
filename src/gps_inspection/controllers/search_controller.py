"""
검색 관련 API 컨트롤러

한국어 특화 검색, 자동완성, 인기 검색어 등의 API 엔드포인트 제공
"""

from flask import Blueprint, request, jsonify, current_app
from typing import Dict, Any, List
import logging

from ..services.search_service import get_search_service
from ..models.wireless_station import WirelessStationDAO


# 블루프린트 생성
search_bp = Blueprint('search', __name__)
logger = logging.getLogger(__name__)


@search_bp.route('/stations', methods=['GET'])
def search_stations():
    """
    통합 무선국 검색
    
    Query Parameters:
        q (str): 검색어 (필수)
        page (int): 페이지 번호 (기본값: 1)
        per_page (int): 페이지당 결과 수 (기본값: 10, 최대: 100)
        user_lat (float): 사용자 위도 (거리순 정렬용, 선택)
        user_lng (float): 사용자 경도 (거리순 정렬용, 선택)
    """
    try:
        # 쿼리 파라미터 파싱
        query = request.args.get('q', '').strip()
        page = request.args.get('page', 1, type=int)
        per_page = min(request.args.get('per_page', 10, type=int), 100)
        user_lat = request.args.get('user_lat', type=float)
        user_lng = request.args.get('user_lng', type=float)
        
        if not query:
            return jsonify({
                'success': False,
                'error': 'MISSING_QUERY',
                'message': '검색어가 필요합니다.'
            }), 400
        
        # 사용자 위치 정보 (선택사항)
        user_location = None
        if user_lat is not None and user_lng is not None:
            user_location = (user_lat, user_lng)
        
        search_service = get_search_service()
        
        # 검색 수행
        search_results, total_count = search_service.search_stations(
            query, user_location, page, per_page
        )
        
        # 응답 데이터 구성
        results_data = []
        for result in search_results:
            result_dict = {
                'station': result.station.to_dict(),
                'relevance_score': result.relevance_score,
                'match_type': result.match_type
            }
            
            if result.distance_meters is not None:
                result_dict['distance_meters'] = result.distance_meters
            
            results_data.append(result_dict)
        
        # 검색 로그 기록 (세션 정보는 나중에 구현)
        search_service.log_search(
            session_id="api_session",
            user_id="api_user",
            query=query,
            search_type="general",
            results_count=len(search_results)
        )
        
        return jsonify({
            'success': True,
            'data': {
                'query': query,
                'results': results_data,
                'pagination': {
                    'page': page,
                    'per_page': per_page,
                    'total': total_count,
                    'pages': (total_count + per_page - 1) // per_page
                },
                'user_location': {
                    'provided': user_location is not None,
                    'latitude': user_lat,
                    'longitude': user_lng
                }
            }
        })
        
    except Exception as e:
        logger.error(f"검색 실패: {e}")
        return jsonify({
            'success': False,
            'error': 'SEARCH_ERROR',
            'message': '검색을 수행할 수 없습니다.'
        }), 500


@search_bp.route('/suggestions', methods=['GET'])
def get_search_suggestions():
    """
    검색어 자동완성
    
    Query Parameters:
        q (str): 입력 중인 검색어 (필수)
        limit (int): 제안 수 제한 (기본값: 5, 최대: 20)
    """
    try:
        query = request.args.get('q', '').strip()
        limit = min(request.args.get('limit', 5, type=int), 20)
        
        if not query:
            return jsonify({
                'success': False,
                'error': 'MISSING_QUERY',
                'message': '검색어가 필요합니다.'
            }), 400
        
        if len(query) < 2:
            return jsonify({
                'success': True,
                'data': {
                    'query': query,
                    'suggestions': []
                }
            })
        
        search_service = get_search_service()
        suggestions = search_service.get_search_suggestions(query, limit)
        
        return jsonify({
            'success': True,
            'data': {
                'query': query,
                'suggestions': suggestions
            }
        })
        
    except Exception as e:
        logger.error(f"자동완성 실패: {e}")
        return jsonify({
            'success': False,
            'error': 'SUGGESTIONS_ERROR',
            'message': '자동완성을 수행할 수 없습니다.'
        }), 500


@search_bp.route('/popular', methods=['GET'])
def get_popular_searches():
    """
    인기 검색어 조회
    
    Query Parameters:
        limit (int): 반환할 검색어 수 (기본값: 10, 최대: 50)
        period (str): 조회 기간 ('day', 'week', 'month', 기본값: 'week')
    """
    try:
        limit = min(request.args.get('limit', 10, type=int), 50)
        period = request.args.get('period', 'week')
        
        if period not in ['day', 'week', 'month']:
            return jsonify({
                'success': False,
                'error': 'INVALID_PERIOD',
                'message': '조회 기간은 day, week, month 중 하나여야 합니다.'
            }), 400
        
        search_service = get_search_service()
        popular_searches = search_service.get_popular_searches(limit)
        
        return jsonify({
            'success': True,
            'data': {
                'popular_searches': popular_searches,
                'period': period,
                'limit': limit
            }
        })
        
    except Exception as e:
        logger.error(f"인기 검색어 조회 실패: {e}")
        return jsonify({
            'success': False,
            'error': 'POPULAR_SEARCHES_ERROR',
            'message': '인기 검색어를 조회할 수 없습니다.'
        }), 500


@search_bp.route('/by-region', methods=['GET'])
def search_by_region():
    """
    지역별 무선국 검색
    
    Query Parameters:
        region (str): 지역명 (필수)
        station_type (str): 무선국 타입 (선택)
        page (int): 페이지 번호 (기본값: 1)
        per_page (int): 페이지당 결과 수 (기본값: 10, 최대: 100)
    """
    try:
        region = request.args.get('region', '').strip()
        station_type = request.args.get('station_type', '').strip()
        page = request.args.get('page', 1, type=int)
        per_page = min(request.args.get('per_page', 10, type=int), 100)
        
        if not region:
            return jsonify({
                'success': False,
                'error': 'MISSING_REGION',
                'message': '지역명이 필요합니다.'
            }), 400
        
        search_service = get_search_service()
        
        # 지역 및 타입별 검색
        stations, total_count = search_service.search_by_region_and_type(
            region, station_type if station_type else None, page, per_page
        )
        
        # 응답 데이터 구성
        station_list = [station.to_dict() for station in stations]
        
        return jsonify({
            'success': True,
            'data': {
                'region': region,
                'station_type': station_type if station_type else None,
                'stations': station_list,
                'pagination': {
                    'page': page,
                    'per_page': per_page,
                    'total': total_count,
                    'pages': (total_count + per_page - 1) // per_page
                }
            }
        })
        
    except Exception as e:
        logger.error(f"지역별 검색 실패: {e}")
        return jsonify({
            'success': False,
            'error': 'REGION_SEARCH_ERROR',
            'message': '지역별 검색을 수행할 수 없습니다.'
        }), 500


@search_bp.route('/by-status', methods=['GET'])
def search_by_status():
    """
    상태별 무선국 검색
    
    Query Parameters:
        status (str): 등록 상태 (필수: '진행중', '완료', '검토중' 등)
        page (int): 페이지 번호 (기본값: 1)
        per_page (int): 페이지당 결과 수 (기본값: 10, 최대: 100)
    """
    try:
        status = request.args.get('status', '').strip()
        page = request.args.get('page', 1, type=int)
        per_page = min(request.args.get('per_page', 10, type=int), 100)
        
        if not status:
            return jsonify({
                'success': False,
                'error': 'MISSING_STATUS',
                'message': '등록 상태가 필요합니다.'
            }), 400
        
        dao = WirelessStationDAO()
        stations, total_count = dao.get_stations_by_status(status, page, per_page)
        
        # 응답 데이터 구성
        station_list = [station.to_dict() for station in stations]
        
        return jsonify({
            'success': True,
            'data': {
                'status': status,
                'stations': station_list,
                'pagination': {
                    'page': page,
                    'per_page': per_page,
                    'total': total_count,
                    'pages': (total_count + per_page - 1) // per_page
                }
            }
        })
        
    except Exception as e:
        logger.error(f"상태별 검색 실패: {e}")
        return jsonify({
            'success': False,
            'error': 'STATUS_SEARCH_ERROR',
            'message': '상태별 검색을 수행할 수 없습니다.'
        }), 500


@search_bp.route('/chosung', methods=['GET'])
def search_by_chosung():
    """
    초성 검색 (한국어 특화)
    
    Query Parameters:
        q (str): 초성 검색어 (필수, 예: 'ㅂㅅㅎ')
        page (int): 페이지 번호 (기본값: 1)
        per_page (int): 페이지당 결과 수 (기본값: 10, 최대: 100)
    """
    try:
        query = request.args.get('q', '').strip()
        page = request.args.get('page', 1, type=int)
        per_page = min(request.args.get('per_page', 10, type=int), 100)
        
        if not query:
            return jsonify({
                'success': False,
                'error': 'MISSING_QUERY',
                'message': '초성 검색어가 필요합니다.'
            }), 400
        
        from ..utils.korean_utils import KoreanUtils
        korean_utils = KoreanUtils()
        
        # 초성 쿼리인지 확인
        if not korean_utils.is_chosung_query(query):
            return jsonify({
                'success': False,
                'error': 'INVALID_CHOSUNG_QUERY',
                'message': '유효한 초성 검색어가 아닙니다.'
            }), 400
        
        search_service = get_search_service()
        
        # 초성 검색 수행 (내부적으로 _chosung_search 메서드 사용)
        search_results, total_count = search_service.search_stations(query, None, page, per_page)
        
        # 초성 매칭 결과만 필터링
        chosung_results = [result for result in search_results if result.match_type == 'chosung']
        
        # 응답 데이터 구성
        results_data = []
        for result in chosung_results:
            # 매칭된 부분 하이라이팅 정보 추가
            station_chosung = korean_utils.extract_chosung(result.station.station_name)
            
            result_dict = {
                'station': result.station.to_dict(),
                'relevance_score': result.relevance_score,
                'match_type': result.match_type,
                'station_chosung': station_chosung,
                'matched_chosung': query
            }
            
            results_data.append(result_dict)
        
        return jsonify({
            'success': True,
            'data': {
                'query': query,
                'results': results_data,
                'pagination': {
                    'page': page,
                    'per_page': per_page,
                    'total': len(chosung_results),
                    'pages': (len(chosung_results) + per_page - 1) // per_page
                }
            }
        })
        
    except Exception as e:
        logger.error(f"초성 검색 실패: {e}")
        return jsonify({
            'success': False,
            'error': 'CHOSUNG_SEARCH_ERROR',
            'message': '초성 검색을 수행할 수 없습니다.'
        }), 500


@search_bp.route('/fuzzy', methods=['GET'])
def fuzzy_search():
    """
    유사도 기반 검색 (오타 허용)
    
    Query Parameters:
        q (str): 검색어 (필수)
        threshold (float): 유사도 임계값 (기본값: 0.7, 범위: 0.0-1.0)
        page (int): 페이지 번호 (기본값: 1)
        per_page (int): 페이지당 결과 수 (기본값: 10, 최대: 100)
    """
    try:
        query = request.args.get('q', '').strip()
        threshold = request.args.get('threshold', 0.7, type=float)
        page = request.args.get('page', 1, type=int)
        per_page = min(request.args.get('per_page', 10, type=int), 100)
        
        if not query:
            return jsonify({
                'success': False,
                'error': 'MISSING_QUERY',
                'message': '검색어가 필요합니다.'
            }), 400
        
        if not (0.0 <= threshold <= 1.0):
            return jsonify({
                'success': False,
                'error': 'INVALID_THRESHOLD',
                'message': '유사도 임계값은 0.0과 1.0 사이여야 합니다.'
            }), 400
        
        from ..utils.korean_utils import KoreanUtils
        from ..models.wireless_station import WirelessStationDAO
        
        korean_utils = KoreanUtils()
        dao = WirelessStationDAO()
        
        # 모든 무선국 조회
        all_stations, _ = dao.search_stations_by_name("", page=1, per_page=1000)
        
        # 유사도 계산 및 필터링
        fuzzy_results = []
        for station in all_stations:
            # 무선국 이름과 유사도 계산
            similarity = korean_utils.calculate_similarity(query, station.station_name)
            
            # 별칭과도 유사도 계산
            if station.station_alias:
                for alias in station.station_alias.split(','):
                    alias_similarity = korean_utils.calculate_similarity(query, alias.strip())
                    similarity = max(similarity, alias_similarity)
            
            # 임계값 이상인 경우 추가
            if similarity >= threshold:
                fuzzy_results.append({
                    'station': station.to_dict(),
                    'similarity': round(similarity, 3),
                    'match_type': 'fuzzy'
                })
        
        # 유사도 순으로 정렬
        fuzzy_results.sort(key=lambda x: x['similarity'], reverse=True)
        
        # 페이지네이션 적용
        total_count = len(fuzzy_results)
        start_idx = (page - 1) * per_page
        end_idx = start_idx + per_page
        paginated_results = fuzzy_results[start_idx:end_idx]
        
        return jsonify({
            'success': True,
            'data': {
                'query': query,
                'threshold': threshold,
                'results': paginated_results,
                'pagination': {
                    'page': page,
                    'per_page': per_page,
                    'total': total_count,
                    'pages': (total_count + per_page - 1) // per_page
                }
            }
        })
        
    except Exception as e:
        logger.error(f"유사도 검색 실패: {e}")
        return jsonify({
            'success': False,
            'error': 'FUZZY_SEARCH_ERROR',
            'message': '유사도 검색을 수행할 수 없습니다.'
        }), 500


@search_bp.route('/statistics', methods=['GET'])
def get_search_statistics():
    """
    검색 통계 정보 조회
    
    Query Parameters:
        period (str): 조회 기간 ('day', 'week', 'month', 기본값: 'week')
    """
    try:
        period = request.args.get('period', 'week')
        
        if period not in ['day', 'week', 'month']:
            return jsonify({
                'success': False,
                'error': 'INVALID_PERIOD',
                'message': '조회 기간은 day, week, month 중 하나여야 합니다.'
            }), 400
        
        # 실제로는 search_logs 테이블에서 통계를 계산해야 함
        # 현재는 더미 데이터 반환
        statistics = {
            'total_searches': 1234,
            'unique_queries': 567,
            'avg_results_per_search': 3.2,
            'most_searched_terms': [
                {'term': '부산항', 'count': 45},
                {'term': '관제탑', 'count': 38},
                {'term': '기지국', 'count': 29},
                {'term': '해운대', 'count': 23},
                {'term': '중계소', 'count': 19}
            ],
            'search_types': {
                'general': 756,
                'region': 289,
                'chosung': 123,
                'fuzzy': 66
            },
            'period': period
        }
        
        return jsonify({
            'success': True,
            'data': statistics
        })
        
    except Exception as e:
        logger.error(f"검색 통계 조회 실패: {e}")
        return jsonify({
            'success': False,
            'error': 'STATISTICS_ERROR',
            'message': '검색 통계를 조회할 수 없습니다.'
        }), 500


@search_bp.route('/nearby-stations', methods=['GET'])
def get_nearby_stations():
    """
    현재 위치 기반 주변 무선국 검색
    
    Query Parameters:
        user_lat (float): 사용자 위도 (필수)
        user_lng (float): 사용자 경도 (필수)
        radius (int): 검색 반경 (미터, 기본값: 1000)
    """
    try:
        user_lat = request.args.get('user_lat', type=float)
        user_lng = request.args.get('user_lng', type=float)
        radius = request.args.get('radius', 1000, type=int) # 기본값 1km
        
        if user_lat is None or user_lng is None:
            return jsonify({
                'success': False,
                'error': 'MISSING_LOCATION',
                'message': '사용자 위도(user_lat)와 경도(user_lng)가 필요합니다.'
            }), 400
        
        if not (0 < radius <= 100000): # 100km 제한
            return jsonify({
                'success': False,
                'error': 'INVALID_RADIUS',
                'message': '검색 반경은 1미터에서 100킬로미터 사이여야 합니다.'
            }), 400
            
        search_service = get_search_service()
        
        # search_service의 search_nearby_stations 호출
        nearby_stations = search_service.search_nearby_stations(
            user_lat, user_lng, radius
        )
        
        # 응답 데이터 구성
        # search_nearby_stations는 이미 딕셔너리 리스트를 반환하므로 그대로 사용
        return jsonify({
            'success': True,
            'data': {
                'user_location': {
                    'latitude': user_lat,
                    'longitude': user_lng,
                    'radius_meters': radius
                },
                'nearby_stations': nearby_stations,
                'total_count': len(nearby_stations)
            }
        })
        
    except Exception as e:
        logger.error(f"주변 무선국 검색 실패: {e}")
        return jsonify({
            'success': False,
            'error': 'NEARBY_SEARCH_ERROR',
            'message': '주변 무선국을 검색할 수 없습니다.'
        }), 500
