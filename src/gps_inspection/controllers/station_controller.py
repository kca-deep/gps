"""
무선국 관련 API 컨트롤러

무선국 CRUD 연산, 위치 기반 중복 확인 등의 API 엔드포인트 제공
"""

from flask import Blueprint, request, jsonify, current_app
from typing import Dict, Any, List
import logging

from ..models.wireless_station import WirelessStation, WirelessStationDAO
from ..services.location_service import get_location_service
from ..services.search_service import get_search_service


# 블루프린트 생성
station_bp = Blueprint('station', __name__)
logger = logging.getLogger(__name__)


@station_bp.route('/', methods=['GET'])
def list_stations():
    """
    무선국 목록 조회
    
    Query Parameters:
        page (int): 페이지 번호 (기본값: 1)
        per_page (int): 페이지당 결과 수 (기본값: 10)
        status (str): 등록 상태 필터
        region (str): 지역 필터
        station_type (str): 무선국 타입 필터
    """
    try:
        # 쿼리 파라미터 파싱
        page = request.args.get('page', 1, type=int)
        per_page = min(request.args.get('per_page', 10, type=int), 100)  # 최대 100개 제한
        status = request.args.get('status')
        region = request.args.get('region')
        station_type = request.args.get('station_type')
        
        dao = WirelessStationDAO()
        search_service = get_search_service()
        
        # 필터에 따른 검색
        if status:
            stations, total = dao.get_stations_by_status(status, page, per_page)
        elif region or station_type:
            stations, total = search_service.search_by_region_and_type(region, station_type, page, per_page)
        else:
            # 기본 목록 조회 (최신순)
            stations, total = dao.search_stations_by_name("", page, per_page)
        
        # 응답 데이터 구성
        station_list = [station.to_dict() for station in stations]
        
        return jsonify({
            'success': True,
            'data': {
                'stations': station_list,
                'pagination': {
                    'page': page,
                    'per_page': per_page,
                    'total': total,
                    'pages': (total + per_page - 1) // per_page
                }
            }
        })
        
    except Exception as e:
        logger.error(f"무선국 목록 조회 실패: {e}")
        return jsonify({
            'success': False,
            'error': 'STATION_LIST_ERROR',
            'message': '무선국 목록을 조회할 수 없습니다.'
        }), 500


@station_bp.route('/<station_id>', methods=['GET'])
def get_station(station_id: str):
    """
    무선국 상세 정보 조회
    
    Path Parameters:
        station_id (str): 무선국 ID
    """
    try:
        dao = WirelessStationDAO()
        station = dao.get_station_by_id(station_id)
        
        if not station:
            return jsonify({
                'success': False,
                'error': 'STATION_NOT_FOUND',
                'message': f'무선국 {station_id}를 찾을 수 없습니다.'
            }), 404
        
        return jsonify({
            'success': True,
            'data': {
                'station': station.to_dict()
            }
        })
        
    except Exception as e:
        logger.error(f"무선국 조회 실패 ({station_id}): {e}")
        return jsonify({
            'success': False,
            'error': 'STATION_GET_ERROR',
            'message': '무선국 정보를 조회할 수 없습니다.'
        }), 500


@station_bp.route('/', methods=['POST'])
def create_station():
    """
    새 무선국 등록
    
    Request Body:
        station_name (str): 무선국 이름 (필수)
        station_type (str): 무선국 타입 (필수)
        latitude (float): 위도 (필수)
        longitude (float): 경도 (필수)
        inspector_id (str): 검사관 ID (필수)
        station_alias (str): 별칭 (선택)
        gps_accuracy (float): GPS 정확도 (선택)
        region_name (str): 지역명 (선택)
        detailed_location (str): 상세 위치 (선택)
        registration_status (str): 등록 상태 (선택)
    """
    try:
        data = request.get_json()
        
        # 필수 필드 검증
        required_fields = ['station_name', 'station_type', 'latitude', 'longitude', 'inspector_id']
        missing_fields = [field for field in required_fields if field not in data]
        
        if missing_fields:
            return jsonify({
                'success': False,
                'error': 'MISSING_REQUIRED_FIELDS',
                'message': f'필수 필드가 누락되었습니다: {", ".join(missing_fields)}'
            }), 400
        
        # 데이터 타입 검증
        try:
            latitude = float(data['latitude'])
            longitude = float(data['longitude'])
        except (ValueError, TypeError):
            return jsonify({
                'success': False,
                'error': 'INVALID_COORDINATES',
                'message': '위도와 경도는 숫자여야 합니다.'
            }), 400
        
        # 위치 검증
        location_service = get_location_service()
        validation_result = location_service.validate_location(
            latitude, longitude, data.get('gps_accuracy')
        )
        
        if not validation_result.is_valid:
            return jsonify({
                'success': False,
                'error': 'INVALID_LOCATION',
                'message': '유효하지 않은 위치입니다.',
                'details': {
                    'warnings': validation_result.warnings,
                    'suggestions': validation_result.suggestions
                }
            }), 400
        
        # 무선국 객체 생성
        station = WirelessStation(
            station_id="",  # 자동 생성
            station_name=data['station_name'],
            station_type=data['station_type'],
            latitude=latitude,
            longitude=longitude,
            inspector_id=data['inspector_id'],
            station_alias=data.get('station_alias'),
            gps_accuracy=data.get('gps_accuracy'),
            region_name=data.get('region_name'),
            detailed_location=data.get('detailed_location'),
            registration_status=data.get('registration_status', '진행중')
        )
        
        # 데이터베이스에 저장
        dao = WirelessStationDAO()
        station_id = dao.create_station(station)
        
        # 생성된 무선국 조회
        created_station = dao.get_station_by_id(station_id)
        
        return jsonify({
            'success': True,
            'data': {
                'station': created_station.to_dict(),
                'location_validation': {
                    'confidence_level': validation_result.confidence_level,
                    'suggestions': validation_result.suggestions
                }
            }
        }), 201
        
    except Exception as e:
        logger.error(f"무선국 생성 실패: {e}")
        return jsonify({
            'success': False,
            'error': 'STATION_CREATE_ERROR',
            'message': '무선국을 생성할 수 없습니다.'
        }), 500


@station_bp.route('/<station_id>', methods=['PUT'])
def update_station(station_id: str):
    """
    무선국 정보 수정
    
    Path Parameters:
        station_id (str): 무선국 ID
        
    Request Body: create_station과 동일 (모든 필드 선택사항)
    """
    try:
        data = request.get_json()
        
        dao = WirelessStationDAO()
        existing_station = dao.get_station_by_id(station_id)
        
        if not existing_station:
            return jsonify({
                'success': False,
                'error': 'STATION_NOT_FOUND',
                'message': f'무선국 {station_id}를 찾을 수 없습니다.'
            }), 404
        
        # 기존 데이터에 새 데이터 업데이트
        updated_data = existing_station.to_dict()
        updated_data.update(data)
        
        # 좌표가 변경된 경우 위치 검증
        if 'latitude' in data or 'longitude' in data:
            try:
                latitude = float(updated_data['latitude'])
                longitude = float(updated_data['longitude'])
                
                location_service = get_location_service()
                validation_result = location_service.validate_location(
                    latitude, longitude, updated_data.get('gps_accuracy')
                )
                
                if not validation_result.is_valid:
                    return jsonify({
                        'success': False,
                        'error': 'INVALID_LOCATION',
                        'message': '유효하지 않은 위치입니다.',
                        'details': {
                            'warnings': validation_result.warnings
                        }
                    }), 400
                    
            except (ValueError, TypeError):
                return jsonify({
                    'success': False,
                    'error': 'INVALID_COORDINATES',
                    'message': '위도와 경도는 숫자여야 합니다.'
                }), 400
        
        # 업데이트된 무선국 객체 생성
        updated_station = WirelessStation.from_dict(updated_data)
        
        # 데이터베이스 업데이트
        success = dao.update_station(updated_station)
        
        if not success:
            return jsonify({
                'success': False,
                'error': 'STATION_UPDATE_ERROR',
                'message': '무선국 정보를 업데이트할 수 없습니다.'
            }), 500
        
        # 업데이트된 무선국 조회
        updated_station = dao.get_station_by_id(station_id)
        
        return jsonify({
            'success': True,
            'data': {
                'station': updated_station.to_dict()
            }
        })
        
    except Exception as e:
        logger.error(f"무선국 업데이트 실패 ({station_id}): {e}")
        return jsonify({
            'success': False,
            'error': 'STATION_UPDATE_ERROR',
            'message': '무선국 정보를 업데이트할 수 없습니다.'
        }), 500


@station_bp.route('/<station_id>', methods=['DELETE'])
def delete_station(station_id: str):
    """
    무선국 삭제
    
    Path Parameters:
        station_id (str): 무선국 ID
    """
    try:
        dao = WirelessStationDAO()
        
        # 무선국 존재 확인
        existing_station = dao.get_station_by_id(station_id)
        if not existing_station:
            return jsonify({
                'success': False,
                'error': 'STATION_NOT_FOUND',
                'message': f'무선국 {station_id}를 찾을 수 없습니다.'
            }), 404
        
        # 삭제 실행
        success = dao.delete_station(station_id)
        
        if not success:
            return jsonify({
                'success': False,
                'error': 'STATION_DELETE_ERROR',
                'message': '무선국을 삭제할 수 없습니다.'
            }), 500
        
        return jsonify({
            'success': True,
            'message': f'무선국 {station_id}가 성공적으로 삭제되었습니다.'
        })
        
    except Exception as e:
        logger.error(f"무선국 삭제 실패 ({station_id}): {e}")
        return jsonify({
            'success': False,
            'error': 'STATION_DELETE_ERROR',
            'message': '무선국을 삭제할 수 없습니다.'
        }), 500


@station_bp.route('/check-duplicate', methods=['POST'])
def check_duplicate():
    """
    위치 기반 중복 확인
    
    Request Body:
        latitude (float): 위도 (필수)
        longitude (float): 경도 (필수)
        station_name (str): 무선국 이름 (필수)
        search_radius (int): 검색 반지름 (선택, 기본값: 100)
    """
    try:
        data = request.get_json()
        
        # 필수 필드 검증
        required_fields = ['latitude', 'longitude', 'station_name']
        missing_fields = [field for field in required_fields if field not in data]
        
        if missing_fields:
            return jsonify({
                'success': False,
                'error': 'MISSING_REQUIRED_FIELDS',
                'message': f'필수 필드가 누락되었습니다: {", ".join(missing_fields)}'
            }), 400
        
        # 데이터 타입 검증
        try:
            latitude = float(data['latitude'])
            longitude = float(data['longitude'])
            search_radius = int(data.get('search_radius', 100))
        except (ValueError, TypeError):
            return jsonify({
                'success': False,
                'error': 'INVALID_PARAMETERS',
                'message': '위도, 경도, 검색 반지름은 숫자여야 합니다.'
            }), 400
        
        location_service = get_location_service()
        
        # 중복 확인 수행
        duplicate_info = location_service.check_location_duplicate(
            latitude, longitude, data['station_name'], search_radius
        )
        
        return jsonify({
            'success': True,
            'data': {
                'has_duplicates': duplicate_info.has_duplicates,
                'nearby_stations': duplicate_info.nearby_stations,
                'similar_name_stations': duplicate_info.similar_name_stations,
                'total_nearby_count': duplicate_info.total_nearby_count,
                'search_radius_meters': duplicate_info.search_radius_meters,
                'recommendations': duplicate_info.recommendations
            }
        })
        
    except Exception as e:
        logger.error(f"중복 확인 실패: {e}")
        return jsonify({
            'success': False,
            'error': 'DUPLICATE_CHECK_ERROR',
            'message': '중복 확인을 수행할 수 없습니다.'
        }), 500


@station_bp.route('/nearby', methods=['GET'])
def get_nearby_stations():
    """
    근처 무선국 조회
    
    Query Parameters:
        latitude (float): 위도 (필수)
        longitude (float): 경도 (필수)
        radius (int): 검색 반지름 (선택, 기본값: 1000)
        detailed (bool): 상세 정보 포함 여부 (선택, 기본값: false)
    """
    try:
        # 쿼리 파라미터 파싱
        latitude = request.args.get('latitude', type=float)
        longitude = request.args.get('longitude', type=float)
        radius = request.args.get('radius', 1000, type=int)
        detailed = request.args.get('detailed', 'false').lower() == 'true'
        
        if latitude is None or longitude is None:
            return jsonify({
                'success': False,
                'error': 'MISSING_COORDINATES',
                'message': '위도와 경도가 필요합니다.'
            }), 400
        
        location_service = get_location_service()
        
        if detailed:
            # 상세 정보 조회
            result = location_service.get_nearby_stations_detailed(latitude, longitude, radius)
        else:
            # 기본 근처 검색
            result = location_service.search_nearby_stations(latitude, longitude, radius)
        
        return jsonify({
            'success': True,
            'data': result
        })
        
    except Exception as e:
        logger.error(f"근처 무선국 조회 실패: {e}")
        return jsonify({
            'success': False,
            'error': 'NEARBY_SEARCH_ERROR',
            'message': '근처 무선국을 조회할 수 없습니다.'
        }), 500


@station_bp.route('/validate-location', methods=['POST'])
def validate_location():
    """
    위치 정보 검증
    
    Request Body:
        latitude (float): 위도 (필수)
        longitude (float): 경도 (필수)
        accuracy_meters (float): GPS 정확도 (선택)
    """
    try:
        data = request.get_json()
        
        # 필수 필드 검증
        if 'latitude' not in data or 'longitude' not in data:
            return jsonify({
                'success': False,
                'error': 'MISSING_COORDINATES',
                'message': '위도와 경도가 필요합니다.'
            }), 400
        
        try:
            latitude = float(data['latitude'])
            longitude = float(data['longitude'])
            accuracy_meters = data.get('accuracy_meters')
            if accuracy_meters is not None:
                accuracy_meters = float(accuracy_meters)
        except (ValueError, TypeError):
            return jsonify({
                'success': False,
                'error': 'INVALID_COORDINATES',
                'message': '위도와 경도는 숫자여야 합니다.'
            }), 400
        
        location_service = get_location_service()
        validation_result = location_service.validate_location(latitude, longitude, accuracy_meters)
        
        return jsonify({
            'success': True,
            'data': {
                'is_valid': validation_result.is_valid,
                'accuracy_meters': validation_result.accuracy_meters,
                'confidence_level': validation_result.confidence_level,
                'warnings': validation_result.warnings,
                'suggestions': validation_result.suggestions
            }
        })
        
    except Exception as e:
        logger.error(f"위치 검증 실패: {e}")
        return jsonify({
            'success': False,
            'error': 'LOCATION_VALIDATION_ERROR',
            'message': '위치 검증을 수행할 수 없습니다.'
        }), 500 