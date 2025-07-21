"""
위치 기반 중복 확인 서비스

GPS 좌표를 기반으로 주변 무선국을 검색하고 중복 등록을 방지하는 서비스
- 반경 내 기존 무선국 검색
- 유사 명칭 확인
- 중복 등록 방지 로직
- 위치 정확도 검증
"""

import logging
import math
import requests # requests 라이브러리 추가
from typing import List, Dict, Any, Tuple, Optional
from dataclasses import dataclass
from datetime import datetime

from ..models.wireless_station import WirelessStationDAO, WirelessStation
from ..models.database import GeoUtils
from ..utils.korean_utils import KoreanUtils
from ..utils.cache_utils import SimpleCache
from config.settings import Config # Config 클래스 임포트


@dataclass
class LocationDuplicateInfo:
    """위치 중복 정보 데이터 클래스"""
    
    has_duplicates: bool
    nearby_stations: List[Dict[str, Any]]
    similar_name_stations: List[Dict[str, Any]]
    total_nearby_count: int
    search_radius_meters: int
    recommendations: List[str]


@dataclass
class LocationValidationResult:
    """위치 검증 결과 데이터 클래스"""
    
    is_valid: bool
    accuracy_meters: Optional[float]
    confidence_level: str  # high, medium, low
    warnings: List[str]
    suggestions: List[str]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "is_valid": self.is_valid,
            "accuracy_meters": self.accuracy_meters,
            "confidence_level": self.confidence_level,
            "warnings": self.warnings,
            "suggestions": self.suggestions
        }


class LocationService:
    """위치 기반 서비스 클래스"""
    
    def __init__(self):
        """위치 서비스 초기화"""
        self.dao = WirelessStationDAO()
        self.korean_utils = KoreanUtils()
        self.cache = SimpleCache(ttl_seconds=60)  # 1분 캐시 (위치는 자주 변동)
        self.logger = logging.getLogger(__name__)
        
        # 기본 설정
        self.default_search_radius = 100  # 미터
        self.max_search_radius = 5000  # 미터
        self.similarity_threshold = 0.7  # 유사도 임계값
    
    def check_location_duplicate(self, latitude: float, longitude: float, 
                                station_name: str, search_radius: int = None) -> LocationDuplicateInfo:
        """
        위치 기반 중복 확인
        
        Args:
            latitude: 위도
            longitude: 경도
            station_name: 등록하려는 무선국 이름
            search_radius: 검색 반지름 (미터)
            
        Returns:
            위치 중복 정보
        """
        if search_radius is None:
            search_radius = self.default_search_radius
        
        # 캐시 확인
        cache_key = f"location_dup_{latitude}_{longitude}_{search_radius}_{station_name}"
        cached_result = self.cache.get(cache_key)
        if cached_result:
            return cached_result
        
        try:
            # 1. 근처 무선국 검색
            nearby_stations = self.dao.find_nearby_stations(latitude, longitude, search_radius)
            
            # 2. 유사 명칭 무선국 검색
            similar_name_stations = self._find_similar_name_stations(station_name, nearby_stations)
            
            # 3. 추천사항 생성
            recommendations = self._generate_recommendations(
                nearby_stations, similar_name_stations, station_name
            )
            
            # 4. 중복 여부 결정
            has_duplicates = len(nearby_stations) > 0 or len(similar_name_stations) > 0
            
            result = LocationDuplicateInfo(
                has_duplicates=has_duplicates,
                nearby_stations=nearby_stations,
                similar_name_stations=similar_name_stations,
                total_nearby_count=len(nearby_stations),
                search_radius_meters=search_radius,
                recommendations=recommendations
            )
            
            # 캐싱
            self.cache.set(cache_key, result, ttl_seconds=60)
            
            self.logger.info(f"위치 중복 확인 완료: {latitude}, {longitude} - 중복 {has_duplicates}")
            
            return result
            
        except Exception as e:
            self.logger.error(f"위치 중복 확인 실패: {e}")
            # 실패 시 안전한 기본값 반환
            return LocationDuplicateInfo(
                has_duplicates=False,
                nearby_stations=[],
                similar_name_stations=[],
                total_nearby_count=0,
                search_radius_meters=search_radius,
                recommendations=["시스템 오류로 인해 중복 확인을 완료할 수 없습니다. 수동 확인을 권장합니다."]
            )
    
    def _find_similar_name_stations(self, target_name: str, 
                                   exclude_stations: List[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        """
        유사 명칭 무선국 검색
        
        Args:
            target_name: 대상 무선국 이름
            exclude_stations: 제외할 무선국 리스트 (이미 근처 검색에서 찾은 것들)
            
        Returns:
            유사 명칭 무선국 리스트
        """
        if not target_name:
            return []
        
        # 제외할 무선국 ID 추출
        exclude_ids = set()
        if exclude_stations:
            exclude_ids = {station['station_id'] for station in exclude_stations}
        
        # 전체 무선국에서 유사 명칭 검색
        all_stations, _ = self.dao.search_stations_by_name("", page=1, per_page=1000)
        
        similar_stations = []
        for station in all_stations:
            if station.station_id in exclude_ids:
                continue
            
            # 유사도 계산
            similarity = self.korean_utils.calculate_similarity(target_name, station.station_name)
            
            # 별칭도 확인
            if station.station_alias:
                for alias in station.station_alias.split(','):
                    alias_similarity = self.korean_utils.calculate_similarity(target_name, alias.strip())
                    similarity = max(similarity, alias_similarity)
            
            # 임계값 이상인 경우 추가
            if similarity >= self.similarity_threshold:
                station_dict = station.to_dict()
                station_dict['name_similarity'] = round(similarity, 3)
                similar_stations.append(station_dict)
        
        # 유사도 순으로 정렬
        similar_stations.sort(key=lambda x: x['name_similarity'], reverse=True)
        
        return similar_stations[:10]  # 최대 10개까지
    
    def _generate_recommendations(self, nearby_stations: List[Dict[str, Any]], 
                                 similar_name_stations: List[Dict[str, Any]], 
                                 station_name: str) -> List[str]:
        """
        추천사항 생성
        
        Args:
            nearby_stations: 근처 무선국 리스트
            similar_name_stations: 유사 명칭 무선국 리스트
            station_name: 등록하려는 무선국 이름
            
        Returns:
            추천사항 리스트
        """
        recommendations = []
        
        # 근처 무선국이 있는 경우
        if nearby_stations:
            if len(nearby_stations) == 1:
                nearest = nearby_stations[0]
                recommendations.append(
                    f"반경 {self.default_search_radius}m 내에 '{nearest['station_name']}' "
                    f"무선국이 {nearest['distance_meters']:.1f}m 거리에 있습니다."
                )
            else:
                recommendations.append(
                    f"반경 {self.default_search_radius}m 내에 {len(nearby_stations)}개의 "
                    f"무선국이 이미 등록되어 있습니다."
                )
            
            recommendations.append("기존 무선국 정보를 확인하여 중복 등록이 아닌지 검토해주세요.")
        
        # 유사 명칭 무선국이 있는 경우
        if similar_name_stations:
            most_similar = similar_name_stations[0]
            recommendations.append(
                f"'{most_similar['station_name']}'와 유사한 이름입니다. "
                f"(유사도: {most_similar['name_similarity']:.1%})"
            )
            recommendations.append("기존 무선국과 다른 무선국인지 확인해주세요.")
        
        # 아무 문제없는 경우
        if not nearby_stations and not similar_name_stations:
            recommendations.append("주변에 중복되는 무선국이 없습니다. 등록을 진행하셔도 됩니다.")
        
        # 일반적인 권장사항
        if nearby_stations or similar_name_stations:
            recommendations.append("신규 등록 또는 기존 정보 수정 중 선택해주세요.")
        
        return recommendations
    
    def validate_location(self, latitude: float, longitude: float, 
                         accuracy_meters: float = None) -> LocationValidationResult:
        """
        위치 정보 검증
        
        Args:
            latitude: 위도
            longitude: 경도
            accuracy_meters: GPS 정확도 (미터)
            
        Returns:
            위치 검증 결과
        """
        warnings = []
        suggestions = []
        
        # 1. 좌표 범위 검증
        if not (-90 <= latitude <= 90):
            warnings.append(f"위도가 유효 범위를 벗어났습니다: {latitude}")
            
        if not (-180 <= longitude <= 180):
            warnings.append(f"경도가 유효 범위를 벗어났습니다: {longitude}")
        
        # 2. 한국 영역 내 검증 (대략적)
        korea_bounds = {
            'min_lat': 33.0, 'max_lat': 38.6,
            'min_lng': 124.5, 'max_lng': 132.0
        }
        
        if not (korea_bounds['min_lat'] <= latitude <= korea_bounds['max_lat'] and
                korea_bounds['min_lng'] <= longitude <= korea_bounds['max_lng']):
            warnings.append("한국 영역을 벗어난 좌표입니다.")
            suggestions.append("좌표를 다시 확인해주세요.")
        
        # 3. GPS 정확도 검증
        confidence_level = "high"
        if accuracy_meters is not None:
            if accuracy_meters > 100:
                confidence_level = "low"
                warnings.append(f"GPS 정확도가 낮습니다: {accuracy_meters:.1f}m")
                suggestions.append("GPS 신호가 좋은 곳에서 다시 측정해주세요.")
            elif accuracy_meters > 20:
                confidence_level = "medium"
                suggestions.append(f"GPS 정확도: {accuracy_meters:.1f}m - 양호")
            else:
                suggestions.append(f"GPS 정확도: {accuracy_meters:.1f}m - 우수")
        
        # 4. 해상/산간지역 검증 (간단한 휴리스틱)
        # 실제로는 지도 API나 지형 데이터를 사용해야 함
        
        is_valid = len(warnings) == 0
        
        return LocationValidationResult(
            is_valid=is_valid,
            accuracy_meters=accuracy_meters,
            confidence_level=confidence_level,
            warnings=warnings,
            suggestions=suggestions
        )
    
    def get_nearby_stations_detailed(self, latitude: float, longitude: float, 
                                   radius_meters: int = None) -> Dict[str, Any]:
        """
        상세한 근처 무선국 정보 조회
        
        Args:
            latitude: 위도
            longitude: 경도
            radius_meters: 검색 반지름
            
        Returns:
            상세 근처 무선국 정보
        """
        if radius_meters is None:
            radius_meters = self.default_search_radius
        
        # 기본 근처 검색
        nearby_stations = self.dao.find_nearby_stations(latitude, longitude, radius_meters)
        
        # 거리별 그룹화
        distance_groups = {
            'very_close': [],    # 50m 이내
            'close': [],         # 50-100m
            'nearby': [],        # 100-500m
            'distant': []        # 500m 이상
        }
        
        for station in nearby_stations:
            distance = station['distance_meters']
            if distance <= 50:
                distance_groups['very_close'].append(station)
            elif distance <= 100:
                distance_groups['close'].append(station)
            elif distance <= 500:
                distance_groups['nearby'].append(station)
            else:
                distance_groups['distant'].append(station)
        
        # 타입별 분류
        type_groups = {}
        for station in nearby_stations:
            station_type = station['station_type']
            if station_type not in type_groups:
                type_groups[station_type] = []
            type_groups[station_type].append(station)
        
        return {
            'total_count': len(nearby_stations),
            'search_radius': radius_meters,
            'distance_groups': distance_groups,
            'type_groups': type_groups,
            'all_stations': nearby_stations
        }
    
    def suggest_alternative_locations(self, latitude: float, longitude: float, 
                                    search_radius: int = None) -> List[Dict[str, Any]]:
        """
        대안 위치 제안
        
        Args:
            latitude: 현재 위도
            longitude: 현재 경도
            search_radius: 검색 반지름
            
        Returns:
            대안 위치 리스트
        """
        if search_radius is None:
            search_radius = self.default_search_radius
        
        alternatives = []
        
        # 현재 위치 주변의 빈 공간 찾기 (간단한 그리드 검색)
        search_step = search_radius / 4  # 1/4 반지름씩 이동
        offsets = [
            (search_step, 0), (-search_step, 0),  # 동서
            (0, search_step), (0, -search_step),  # 남북
            (search_step, search_step), (-search_step, -search_step),  # 대각선
            (search_step, -search_step), (-search_step, search_step)
        ]
        
        for lat_offset, lng_offset in offsets:
            # 미터를 위도/경도로 변환 (대략적)
            lat_offset_deg = lat_offset / 111000
            lng_offset_deg = lng_offset / (111000 * abs(math.cos(math.radians(latitude))))
            
            alt_lat = latitude + lat_offset_deg
            alt_lng = longitude + lng_offset_deg
            
            # 대안 위치 주변 확인
            nearby = self.dao.find_nearby_stations(alt_lat, alt_lng, search_radius // 2)
            
            if len(nearby) == 0:  # 빈 공간 발견
                distance_from_original = GeoUtils.haversine_distance(
                    latitude, longitude, alt_lat, alt_lng
                )
                
                alternatives.append({
                    'latitude': alt_lat,
                    'longitude': alt_lng,
                    'distance_from_original': round(distance_from_original, 1),
                    'reason': '주변에 다른 무선국이 없는 위치'
                })
        
        # 거리순 정렬
        alternatives.sort(key=lambda x: x['distance_from_original'])
        
        return alternatives[:5]  # 최대 5개까지

    def get_address_from_coordinates(self, latitude: float, longitude: float) -> Dict[str, Any]:
        """
        GPS 좌표를 주소로 변환 (티맵 API 연동)
        
        Args:
            latitude: 위도
            longitude: 경도
            
        Returns:
            주소 변환 결과
        """
        try:
            # 좌표 유효성 검증
            if not self._validate_coordinates(latitude, longitude):
                return {
                    "success": False,
                    "error": "유효하지 않은 GPS 좌표입니다.",
                    "latitude": latitude,
                    "longitude": longitude
                }
            
            # 티맵 API 호출
            address_info = self._call_tmap_reverse_geocoding_api(latitude, longitude)
            
            if address_info:
                return {
                    "success": True,
                    "address": address_info["address"],
                    "region_name": address_info["region_name"],
                    "detailed_location": address_info["detailed_location"],
                    "latitude": latitude,
                    "longitude": longitude,
                    "accuracy": "high" # TMap API를 사용하므로 정확도 높음으로 간주
                }
            else:
                return {
                    "success": False,
                    "error": "TMap API를 통해 주소 변환에 실패했습니다.",
                    "latitude": latitude,
                    "longitude": longitude
                }
            
        except requests.exceptions.RequestException as e:
            self.logger.error(f"TMap API 요청 오류: {e}")
            return {
                "success": False,
                "error": f"TMap API 요청 중 네트워크 오류가 발생했습니다: {e}",
                "latitude": latitude,
                "longitude": longitude
            }
        except Exception as e:
            self.logger.error(f"주소 변환 오류: {e}")
            return {
                "success": False,
                "error": f"주소 변환 중 알 수 없는 오류가 발생했습니다: {e}",
                "latitude": latitude,
                "longitude": longitude
            }
    
    def _validate_coordinates(self, latitude: float, longitude: float) -> bool:
        """GPS 좌표 유효성 검증 (한국 영역 내)"""
        # 한국의 대략적인 위도/경도 범위
        # 실제 TMap API는 더 정확한 유효성 검증을 수행할 것이므로, 여기서는 기본적인 범위만 확인
        if not (33.0 <= latitude <= 39.0):
            return False
        if not (124.0 <= longitude <= 132.0):
            return False
        return True

    def _call_tmap_reverse_geocoding_api(self, latitude: float, longitude: float) -> Optional[Dict[str, str]]:
        """
        TMap Reverse Geocoding API 호출
        GPS 좌표를 주소로 변환
        """
        api_key = Config.TMAP_API_KEY
        if not api_key:
            self.logger.error("TMAP_API_KEY가 설정되지 않았습니다.")
            return None

        url = "https://apis.openapi.sk.com/tmap/geo/reversegeocoding"
        params = {
            "lat": latitude,
            "lon": longitude,
            "coordType": "WGS84GEO",  # 위도/경도 좌표계
            "addressType": "A00",     # 법정동, 도로명 주소 모두 포함
            "version": "1",           # API 버전
            "appKey": api_key
        }

        try:
            response = requests.get(url, params=params)
            response.raise_for_status()  # HTTP 오류 발생 시 예외 발생

            data = response.json()
            
            # API 응답 구조에 따라 주소 정보 파싱
            # TMap Reverse Geocoding API 응답 예시를 기반으로 파싱
            # https://apis.openapi.sk.com/tmap/docs/webservice/docs/reverseGeocoding
            
            address_info = data.get("addressInfo")
            if address_info:
                full_address = f"{address_info.get('fullAddress', '')}"
                
                # 도로명 주소 또는 지번 주소 중 하나를 선택하여 상세 주소 구성
                road_name = address_info.get('roadName', '')
                building_name = address_info.get('buildingName', '')
                
                detailed_location = ""
                if road_name:
                    detailed_location = f"{road_name} {building_name}".strip()
                elif address_info.get('legalDong'):
                    detailed_location = f"{address_info.get('legalDong')} {address_info.get('bunji')}".strip()
                
                return {
                    "address": full_address,
                    "region_name": address_info.get("city_do", "") + " " + address_info.get("gu_gun", ""),
                    "detailed_location": detailed_location
                }
            else:
                self.logger.warning(f"TMap Reverse Geocoding API 응답에 addressInfo가 없습니다: {data}")
                return None

        except requests.exceptions.RequestException as e:
            self.logger.error(f"TMap Reverse Geocoding API 요청 실패: {e}")
            return None
        except ValueError as e:
            self.logger.error(f"TMap Reverse Geocoding API 응답 JSON 파싱 실패: {e}")
            return None
        except Exception as e:
            self.logger.error(f"TMap Reverse Geocoding API 처리 중 알 수 없는 오류 발생: {e}")
            return None
    
    def validate_registration_location(self, latitude: float, longitude: float, 
                                     station_name: str = "", radius: int = 100) -> Dict[str, Any]:
        """
        무선국 등록을 위한 위치 검증
        
        Args:
            latitude: 위도
            longitude: 경도
            station_name: 무선국명 (중복 체크용)
            radius: 중복 체크 반지름 (미터)
            
        Returns:
            검증 결과 및 추천사항
        """
        try:
            result = {
                "valid": True,
                "warnings": [],
                "recommendations": [],
                "nearby_stations": [],
                "address_info": None
            }
            
            # 1. 좌표 유효성 검증
            if not self._validate_coordinates(latitude, longitude):
                result["valid"] = False
                result["warnings"].append("한국 영역 밖의 좌표입니다.")
                result["recommendations"].append("좌표를 다시 확인해 주세요.")
                return result
            
            # 2. 주소 정보 획득
            address_result = self.get_address_from_coordinates(latitude, longitude)
            if address_result["success"]:
                result["address_info"] = address_result
            else:
                result["warnings"].append("주소 변환에 실패했습니다.")
            
            # 3. 근처 무선국 중복 체크
            duplicate_info = self.check_location_duplicate(latitude, longitude, station_name, radius)
            
            if duplicate_info.has_duplicates:
                result["warnings"].append(f"반경 {radius}m 내에 {duplicate_info.total_nearby_count}개의 무선국이 있습니다.")
                result["nearby_stations"] = duplicate_info.nearby_stations
                result["recommendations"].extend(duplicate_info.recommendations)
            
            return result
            
        except Exception as e:
            self.logger.error(f"등록 위치 검증 오류: {e}")
            return {
                "valid": False,
                "warnings": ["위치 검증 중 오류가 발생했습니다."],
                "recommendations": ["다시 시도해 주세요."],
                "nearby_stations": [],
                "address_info": None
            }

    def get_current_pinpoint_info(self, latitude: float, longitude: float, 
                                  search_radius: int = None) -> Dict[str, Any]:
        """
        현재 핀포인트의 상세 정보 조회 (지도 API 연동)
        
        Args:
            latitude: 위도
            longitude: 경도
            search_radius: 주변 무선국 검색 반지름 (미터)
            
        Returns:
            현재 핀포인트의 상세 정보 (주소, 주변 무선국 등)
        """
        if search_radius is None:
            search_radius = self.default_search_radius
            
        try:
            info = {
                "latitude": latitude,
                "longitude": longitude,
                "address_info": None,
                "nearby_stations_summary": None,
                "validation_result": None,
                "success": True,
                "message": "핀포인트 정보 조회가 완료되었습니다."
            }
            
            # 1. 좌표 유효성 검증
            validation_result = self.validate_location(latitude, longitude)
            info["validation_result"] = validation_result.to_dict() # dataclass to dict
            
            if not validation_result.is_valid:
                info["success"] = False
                info["message"] = "유효하지 않거나 한국 영역 밖의 좌표입니다."
                self.logger.warning(f"유효하지 않은 핀포인트 좌표: {latitude}, {longitude}")
                return info
            
            # 2. 주소 정보 획득
            address_result = self.get_address_from_coordinates(latitude, longitude)
            if address_result["success"]:
                info["address_info"] = address_result
            else:
                info["success"] = False
                info["message"] = f"주소 변환 실패: {address_result.get('error', '알 수 없는 오류')}"
                self.logger.error(f"핀포인트 주소 변환 실패: {latitude}, {longitude} - {address_result.get('error')}")
            
            # 3. 주변 무선국 상세 정보 획득
            nearby_detailed = self.get_nearby_stations_detailed(latitude, longitude, radius_meters=search_radius)
            info["nearby_stations_summary"] = {
                "total_count": nearby_detailed["total_count"],
                "search_radius": nearby_detailed["search_radius"],
                "distance_groups": nearby_detailed["distance_groups"],
                "type_groups": nearby_detailed["type_groups"],
                "all_stations": nearby_detailed["all_stations"] # 모든 주변 무선국 포함
            }
            
            self.logger.info(f"핀포인트 정보 조회 완료: {latitude}, {longitude}")
            return info
            
        except Exception as e:
            self.logger.error(f"핀포인트 정보 조회 오류: {e}")
            return {
                "success": False,
                "message": f"핀포인트 정보 조회 중 오류가 발생했습니다: {e}",
                "latitude": latitude,
                "longitude": longitude
            }

    def get_coordinates_from_address(self, address: str) -> Dict[str, Any]:
        """
        주소를 GPS 좌표로 변환 (티맵 API 연동)
        
        Args:
            address: 변환할 주소
            
        Returns:
            좌표 변환 결과
        """
        try:
            if not address or len(address.strip()) < 5:
                return {
                    "success": False,
                    "error": "주소가 너무 짧거나 유효하지 않습니다. 최소 5자 이상 입력해 주세요.",
                    "address": address
                }
            
            # 주소 정규화
            normalized_address = address.strip()
            
            # 티맵 API 호출
            coordinates_info = self._call_tmap_geocoding_api(normalized_address)
            
            if coordinates_info and coordinates_info["success"]:
                # 좌표 유효성 검증
                latitude = coordinates_info["latitude"]
                longitude = coordinates_info["longitude"]
                
                if not self._validate_coordinates(latitude, longitude):
                    return {
                        "success": False,
                        "error": "변환된 좌표가 대한민국 지역을 벗어났습니다.",
                        "address": address,
                        "latitude": latitude,
                        "longitude": longitude
                    }
                
                return {
                    "success": True,
                    "latitude": latitude,
                    "longitude": longitude,
                    "address": normalized_address,
                    "region_name": coordinates_info.get("region_name"),
                    "accuracy": coordinates_info.get("accuracy", "medium"),
                    "confidence": coordinates_info.get("confidence", 0.8)
                }
            else:
                return {
                    "success": False,
                    "error": coordinates_info.get("error", "주소를 좌표로 변환할 수 없습니다.") if coordinates_info else "TMap API 호출 실패",
                    "address": address
                }
                
        except requests.exceptions.RequestException as e:
            self.logger.error(f"TMap API 요청 오류: {e}")
            return {
                "success": False,
                "error": f"TMap API 요청 중 네트워크 오류가 발생했습니다: {e}",
                "address": address
            }
        except Exception as e:
            self.logger.error(f"주소 좌표 변환 오류: {e}")
            return {
                "success": False,
                "error": f"주소 변환 중 알 수 없는 오류가 발생했습니다: {str(e)}",
                "address": address
            }

    def _call_tmap_geocoding_api(self, address: str) -> Optional[Dict[str, Any]]:
        """
        TMap Geocoding API 호출
        주소를 GPS 좌표로 변환
        """
        api_key = Config.TMAP_API_KEY
        if not api_key:
            self.logger.error("TMAP_API_KEY가 설정되지 않았습니다.")
            return None

        url = "https://apis.openapi.sk.com/tmap/geo/geocoding"
        params = {
            "coordType": "WGS84GEO",  # 위도/경도 좌표계
            "addressFlag": "F00",     # 전체 주소 검색
            "version": "1",           # API 버전
            "fullAddress": address,
            "appKey": api_key
        }

        try:
            response = requests.get(url, params=params)
            response.raise_for_status()  # HTTP 오류 발생 시 예외 발생

            data = response.json()
            
            # API 응답 구조에 따라 좌표 정보 파싱
            # TMap Geocoding API 응답 예시를 기반으로 파싱
            # https://apis.openapi.sk.com/tmap/docs/webservice/docs/geocoding
            
            coordinate_info = data.get("coordinateInfo")
            if coordinate_info and coordinate_info.get("coordinate"):
                first_coord = coordinate_info["coordinate"][0] # 첫 번째 결과 사용
                
                latitude = float(first_coord.get("newLat"))
                longitude = float(first_coord.get("newLon"))
                
                return {
                    "success": True,
                    "latitude": latitude,
                    "longitude": longitude,
                    "region_name": f"{first_coord.get('city_do', '')} {first_coord.get('gu_gun', '')}",
                    "accuracy": "high", # TMap API를 사용하므로 정확도 높음으로 간주
                    "confidence": 0.9 # API 결과이므로 높은 신뢰도
                }
            else:
                self.logger.warning(f"TMap Geocoding API 응답에 coordinateInfo가 없습니다: {data}")
                return {
                    "success": False,
                    "error": "주소를 좌표로 변환할 수 없습니다. 더 구체적인 주소를 입력해 주세요."
                }

        except requests.exceptions.RequestException as e:
            self.logger.error(f"TMap Geocoding API 요청 실패: {e}")
            return {
                "success": False,
                "error": f"TMap Geocoding API 요청 중 네트워크 오류가 발생했습니다: {e}"
            }
        except (ValueError, TypeError) as e:
            self.logger.error(f"TMap Geocoding API 응답 JSON 파싱 또는 데이터 변환 실패: {e}")
            return {
                "success": False,
                "error": "TMap API 응답 처리 중 오류가 발생했습니다."
            }
        except Exception as e:
            self.logger.error(f"TMap Geocoding API 처리 중 알 수 없는 오류 발생: {e}")
            return {
                "success": False,
                "error": f"주소 좌표 변환 중 알 수 없는 오류가 발생했습니다: {e}"
            }


# 전역 위치 서비스 인스턴스
location_service = LocationService()


def get_location_service() -> LocationService:
    """위치 서비스 인스턴스 반환"""
    return location_service
