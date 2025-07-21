#!/usr/bin/env python3
"""
위치 서비스 테스트 스크립트

위치 기반 중복 확인, 위치 검증 등의 기능을 테스트
"""

import sys
import os

# 프로젝트 루트를 Python path에 추가
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from gps_inspection.services.location_service import get_location_service, LocationService
from gps_inspection.models.wireless_station import WirelessStation, WirelessStationDAO


def test_location_validation():
    """위치 검증 테스트"""
    print("=== 위치 검증 테스트 ===")
    
    try:
        location_service = get_location_service()
        
        # 1. 정상적인 한국 내 좌표 (부산)
        result = location_service.validate_location(35.1796, 129.0756, accuracy_meters=5.0)
        print(f"✅ 부산 좌표 검증: {result.is_valid}, 신뢰도: {result.confidence_level}")
        if result.suggestions:
            print(f"   제안사항: {result.suggestions[0]}")
        
        # 2. 잘못된 좌표
        result = location_service.validate_location(91.0, 200.0)
        print(f"✅ 잘못된 좌표 검증: {result.is_valid}")
        if result.warnings:
            print(f"   경고: {result.warnings}")
        
        # 3. 한국 영역 밖 좌표
        result = location_service.validate_location(40.0, 140.0)  # 일본 근처
        print(f"✅ 한국 밖 좌표 검증: {result.is_valid}")
        if result.warnings:
            print(f"   경고: {result.warnings[0]}")
        
        # 4. 낮은 GPS 정확도
        result = location_service.validate_location(35.1796, 129.0756, accuracy_meters=150.0)
        print(f"✅ 낮은 정확도 검증: 신뢰도 {result.confidence_level}")
        if result.warnings:
            print(f"   경고: {result.warnings[0]}")
        
        return True
        
    except Exception as e:
        print(f"❌ 위치 검증 테스트 실패: {e}")
        return False


def test_duplicate_check():
    """중복 확인 테스트"""
    print("\n=== 중복 확인 테스트 ===")
    
    try:
        location_service = get_location_service()
        dao = WirelessStationDAO()
        
        # 1. 기존 무선국이 없는 위치에서 중복 확인
        duplicate_info = location_service.check_location_duplicate(
            latitude=35.2000,  # 기존 샘플 데이터와 다른 위치
            longitude=129.2000,
            station_name="새로운무선국"
        )
        
        print(f"✅ 빈 위치 중복 확인: 중복 {duplicate_info.has_duplicates}")
        print(f"   근처 무선국 수: {duplicate_info.total_nearby_count}")
        print(f"   추천사항: {duplicate_info.recommendations[0]}")
        
        # 2. 기존 무선국 근처에서 중복 확인 (부산항관제탑 근처)
        duplicate_info = location_service.check_location_duplicate(
            latitude=35.1796,
            longitude=129.0756,
            station_name="부산항신규무선국",
            search_radius=200
        )
        
        print(f"✅ 기존 무선국 근처 중복 확인: 중복 {duplicate_info.has_duplicates}")
        print(f"   근처 무선국 수: {duplicate_info.total_nearby_count}")
        if duplicate_info.nearby_stations:
            nearest = duplicate_info.nearby_stations[0]
            print(f"   가장 가까운 무선국: {nearest['station_name']} ({nearest['distance_meters']:.1f}m)")
        
        # 3. 유사한 이름으로 중복 확인
        duplicate_info = location_service.check_location_duplicate(
            latitude=35.3000,  # 다른 위치
            longitude=129.3000,
            station_name="부산항관제소"  # 기존 '부산항관제탑'과 유사
        )
        
        print(f"✅ 유사 이름 중복 확인: 중복 {duplicate_info.has_duplicates}")
        if duplicate_info.similar_name_stations:
            similar = duplicate_info.similar_name_stations[0]
            print(f"   유사 무선국: {similar['station_name']} (유사도: {similar['name_similarity']:.3f})")
        
        return True
        
    except Exception as e:
        print(f"❌ 중복 확인 테스트 실패: {e}")
        return False


def test_nearby_stations_detailed():
    """상세 근처 무선국 조회 테스트"""
    print("\n=== 상세 근처 무선국 조회 테스트 ===")
    
    try:
        location_service = get_location_service()
        
        # 부산 지역에서 근처 무선국 조회
        detailed_info = location_service.get_nearby_stations_detailed(
            latitude=35.1796,
            longitude=129.0756,
            radius_meters=5000  # 5km 반경
        )
        
        print(f"✅ 상세 조회 완료: 총 {detailed_info['total_count']}개")
        print(f"   검색 반지름: {detailed_info['search_radius']}m")
        
        # 거리별 그룹 정보
        distance_groups = detailed_info['distance_groups']
        print("   거리별 그룹:")
        print(f"     매우 가까움 (50m 이내): {len(distance_groups['very_close'])}개")
        print(f"     가까움 (50-100m): {len(distance_groups['close'])}개")
        print(f"     근처 (100-500m): {len(distance_groups['nearby'])}개")
        print(f"     먼 거리 (500m+): {len(distance_groups['distant'])}개")
        
        # 타입별 그룹 정보
        type_groups = detailed_info['type_groups']
        print("   타입별 그룹:")
        for station_type, stations in type_groups.items():
            print(f"     {station_type}: {len(stations)}개")
        
        return True
        
    except Exception as e:
        print(f"❌ 상세 근처 무선국 조회 테스트 실패: {e}")
        return False


def test_alternative_locations():
    """대안 위치 제안 테스트"""
    print("\n=== 대안 위치 제안 테스트 ===")
    
    try:
        location_service = get_location_service()
        
        # 기존 무선국이 있는 위치에서 대안 위치 찾기
        alternatives = location_service.suggest_alternative_locations(
            latitude=35.1796,
            longitude=129.0756,
            search_radius=100
        )
        
        print(f"✅ 대안 위치 {len(alternatives)}개 발견")
        
        for i, alt in enumerate(alternatives, 1):
            print(f"   {i}. 위치: ({alt['latitude']:.6f}, {alt['longitude']:.6f})")
            print(f"      원래 위치에서 거리: {alt['distance_from_original']:.1f}m")
            print(f"      이유: {alt['reason']}")
        
        return True
        
    except Exception as e:
        print(f"❌ 대안 위치 제안 테스트 실패: {e}")
        return False


def test_cache_performance():
    """캐시 성능 테스트"""
    print("\n=== 캐시 성능 테스트 ===")
    
    try:
        import time
        location_service = get_location_service()
        
        # 첫 번째 호출 (캐시 없음)
        start_time = time.time()
        result1 = location_service.check_location_duplicate(35.1796, 129.0756, "테스트무선국")
        first_call_time = time.time() - start_time
        
        # 두 번째 호출 (캐시 있음)
        start_time = time.time()
        result2 = location_service.check_location_duplicate(35.1796, 129.0756, "테스트무선국")
        second_call_time = time.time() - start_time
        
        print(f"✅ 첫 번째 호출 시간: {first_call_time:.3f}초")
        print(f"✅ 두 번째 호출 시간: {second_call_time:.3f}초")
        print(f"✅ 캐시 효과: {first_call_time/second_call_time:.1f}배 빨라짐")
        
        # 결과가 동일한지 확인
        if (result1.has_duplicates == result2.has_duplicates and
            result1.total_nearby_count == result2.total_nearby_count):
            print("✅ 캐시된 결과가 일치함")
        else:
            print("❌ 캐시된 결과가 일치하지 않음")
            return False
        
        return True
        
    except Exception as e:
        print(f"❌ 캐시 성능 테스트 실패: {e}")
        return False


def demonstrate_duplicate_scenarios():
    """중복 시나리오 시연"""
    print("\n=== 중복 시나리오 시연 ===")
    
    scenarios = [
        {
            "name": "시나리오 1: 완전히 새로운 위치",
            "lat": 37.5665, "lng": 126.9780,  # 서울
            "station_name": "서울중앙무선국"
        },
        {
            "name": "시나리오 2: 기존 무선국 매우 근처",
            "lat": 35.1800, "lng": 129.0760,  # 부산항관제탑 근처
            "station_name": "부산항보조무선국"
        },
        {
            "name": "시나리오 3: 유사한 이름의 무선국",
            "lat": 35.4000, "lng": 129.4000,  # 다른 위치
            "station_name": "부산항중앙관제탑"  # 기존과 유사한 이름
        }
    ]
    
    try:
        location_service = get_location_service()
        
        for scenario in scenarios:
            print(f"\n--- {scenario['name']} ---")
            
            result = location_service.check_location_duplicate(
                scenario['lat'], scenario['lng'], scenario['station_name']
            )
            
            print(f"등록 시도: '{scenario['station_name']}'")
            print(f"위치: ({scenario['lat']}, {scenario['lng']})")
            print(f"중복 여부: {'있음' if result.has_duplicates else '없음'}")
            
            for i, recommendation in enumerate(result.recommendations, 1):
                print(f"  {i}. {recommendation}")
        
        return True
        
    except Exception as e:
        print(f"❌ 시나리오 시연 실패: {e}")
        return False


def main():
    """메인 테스트 함수"""
    print("🚀 위치 기반 중복 확인 서비스 테스트 시작\n")
    
    tests = [
        ("위치 검증", test_location_validation),
        ("중복 확인", test_duplicate_check),
        ("상세 근처 무선국 조회", test_nearby_stations_detailed),
        ("대안 위치 제안", test_alternative_locations),
        ("캐시 성능", test_cache_performance),
        ("중복 시나리오 시연", demonstrate_duplicate_scenarios),
    ]
    
    passed = 0
    total = len(tests)
    
    for test_name, test_func in tests:
        try:
            if test_func():
                passed += 1
            print()  # 빈 줄 추가
        except Exception as e:
            print(f"❌ {test_name} 테스트 중 예외 발생: {e}\n")
    
    print(f"🏁 테스트 완료: {passed}/{total} 통과")
    
    if passed == total:
        print("🎉 모든 위치 서비스 테스트가 성공했습니다!")
        return True
    else:
        print("⚠️  일부 테스트가 실패했습니다.")
        return False


if __name__ == "__main__":
    main() 