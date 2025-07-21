#!/usr/bin/env python3
"""
기본 기능 테스트 스크립트

데이터베이스 초기화, 무선국 등록, 검색 기능 등을 테스트
"""

import sys
import os

# 프로젝트 루트를 Python path에 추가
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from gps_inspection.models.database import get_db_manager
from gps_inspection.models.wireless_station import WirelessStation, WirelessStationDAO
from gps_inspection.utils.korean_utils import KoreanUtils
from gps_inspection.utils.cache_utils import SimpleCache


def test_database_initialization():
    """데이터베이스 초기화 테스트"""
    print("=== 데이터베이스 초기화 테스트 ===")
    
    try:
        db_manager = get_db_manager()
        print("✅ 데이터베이스 초기화 성공")
        
        # 테이블 존재 확인
        tables = db_manager.execute_query("""
            SELECT name FROM sqlite_master 
            WHERE type='table' AND name NOT LIKE 'sqlite_%'
        """)
        
        table_names = [table['name'] for table in tables]
        print(f"📋 생성된 테이블: {table_names}")
        
        expected_tables = ['wireless_stations', 'chat_sessions', 'search_logs', 'safety_info']
        for table in expected_tables:
            if table in table_names:
                print(f"   ✅ {table}")
            else:
                print(f"   ❌ {table} - 누락")
        
        return True
        
    except Exception as e:
        print(f"❌ 데이터베이스 초기화 실패: {e}")
        return False


def test_wireless_station_crud():
    """무선국 CRUD 테스트"""
    print("\n=== 무선국 CRUD 테스트 ===")
    
    try:
        dao = WirelessStationDAO()
        
        # 테스트 무선국 생성
        test_station = WirelessStation(
            station_id="",  # 자동 생성
            station_name="부산항관제탑",
            station_alias="부산항,관제탑",
            station_type="관제탑",
            latitude=35.1796,
            longitude=129.0756,
            region_name="부산광역시",
            detailed_location="중구 중앙동",
            inspector_id="INS001"
        )
        
        # 1. 생성 테스트
        station_id = dao.create_station(test_station)
        print(f"✅ 무선국 생성 성공: {station_id}")
        
        # 2. 조회 테스트
        retrieved_station = dao.get_station_by_id(station_id)
        if retrieved_station:
            print(f"✅ 무선국 조회 성공: {retrieved_station.station_name}")
        else:
            print("❌ 무선국 조회 실패")
            return False
        
        # 3. 검색 테스트
        search_results, total = dao.search_stations_by_name("부산항")
        print(f"✅ 이름 검색 성공: {total}개 결과")
        
        # 4. 근처 검색 테스트
        nearby_stations = dao.find_nearby_stations(35.1796, 129.0756, 1000)
        print(f"✅ 근처 검색 성공: {len(nearby_stations)}개 결과")
        
        # 5. 업데이트 테스트
        retrieved_station.registration_status = "완료"
        success = dao.update_station(retrieved_station)
        if success:
            print("✅ 무선국 업데이트 성공")
        else:
            print("❌ 무선국 업데이트 실패")
        
        return True
        
    except Exception as e:
        print(f"❌ 무선국 CRUD 테스트 실패: {e}")
        return False


def test_korean_utils():
    """한국어 유틸리티 테스트"""
    print("\n=== 한국어 유틸리티 테스트 ===")
    
    try:
        korean_utils = KoreanUtils()
        
        # 1. 초성 추출 테스트
        test_text = "부산항관제탑"
        chosung = korean_utils.extract_chosung(test_text)
        print(f"✅ 초성 추출: '{test_text}' → '{chosung}'")
        
        # 2. 초성 쿼리 판별 테스트
        chosung_query = "ㅂㅅㅎ"
        is_chosung = korean_utils.is_chosung_query(chosung_query)
        print(f"✅ 초성 쿼리 판별: '{chosung_query}' → {is_chosung}")
        
        # 3. 편집거리 계산 테스트
        s1, s2 = "부산항", "부산항구"
        distance = korean_utils.simple_edit_distance(s1, s2)
        print(f"✅ 편집거리: '{s1}' vs '{s2}' → {distance}")
        
        # 4. 유사도 계산 테스트
        similarity = korean_utils.calculate_similarity(s1, s2)
        print(f"✅ 유사도: '{s1}' vs '{s2}' → {similarity:.2f}")
        
        # 5. 텍스트 정규화 테스트
        messy_text = "  부산항   관제탑  !@#  "
        normalized = korean_utils.normalize_text(messy_text)
        print(f"✅ 정규화: '{messy_text}' → '{normalized}'")
        
        return True
        
    except Exception as e:
        print(f"❌ 한국어 유틸리티 테스트 실패: {e}")
        return False


def test_cache_utils():
    """캐시 유틸리티 테스트"""
    print("\n=== 캐시 유틸리티 테스트 ===")
    
    try:
        cache = SimpleCache(max_size=100, ttl_seconds=10)
        
        # 1. 저장/조회 테스트
        cache.set("test_key", "test_value")
        value = cache.get("test_key")
        if value == "test_value":
            print("✅ 캐시 저장/조회 성공")
        else:
            print("❌ 캐시 저장/조회 실패")
            return False
        
        # 2. 존재 확인 테스트
        exists = cache.exists("test_key")
        print(f"✅ 존재 확인: {exists}")
        
        # 3. 통계 정보 테스트
        stats = cache.get_stats()
        print(f"✅ 캐시 통계: {stats}")
        
        # 4. 삭제 테스트
        deleted = cache.delete("test_key")
        print(f"✅ 캐시 삭제: {deleted}")
        
        return True
        
    except Exception as e:
        print(f"❌ 캐시 유틸리티 테스트 실패: {e}")
        return False


def create_sample_data():
    """샘플 데이터 생성"""
    print("\n=== 샘플 데이터 생성 ===")
    
    try:
        dao = WirelessStationDAO()
        
        sample_stations = [
            {
                "station_name": "해운대기지국",
                "station_alias": "해운대,기지국",
                "station_type": "기지국",
                "latitude": 35.1587,
                "longitude": 129.1603,
                "region_name": "부산광역시",
                "detailed_location": "해운대구 우동",
                "inspector_id": "INS001"
            },
            {
                "station_name": "광안리중계소",
                "station_alias": "광안리,중계소",
                "station_type": "중계소",
                "latitude": 35.1532,
                "longitude": 129.1186,
                "region_name": "부산광역시",
                "detailed_location": "수영구 광안동",
                "inspector_id": "INS002"
            },
            {
                "station_name": "김해공항관제탑",
                "station_alias": "김해공항,관제탑",
                "station_type": "관제탑",
                "latitude": 35.1795,
                "longitude": 128.9384,
                "region_name": "부산광역시",
                "detailed_location": "강서구 대저동",
                "inspector_id": "INS001"
            }
        ]
        
        created_count = 0
        for station_data in sample_stations:
            station = WirelessStation(
                station_id="",  # 자동 생성
                **station_data
            )
            
            station_id = dao.create_station(station)
            created_count += 1
            print(f"   📡 {station.station_name} ({station_id})")
        
        print(f"✅ 샘플 데이터 생성 완료: {created_count}개")
        return True
        
    except Exception as e:
        print(f"❌ 샘플 데이터 생성 실패: {e}")
        return False


def main():
    """메인 테스트 함수"""
    print("🚀 GPS 무선국 검사 시스템 기본 기능 테스트 시작\n")
    
    tests = [
        ("데이터베이스 초기화", test_database_initialization),
        ("무선국 CRUD", test_wireless_station_crud),
        ("한국어 유틸리티", test_korean_utils),
        ("캐시 유틸리티", test_cache_utils),
        ("샘플 데이터 생성", create_sample_data),
    ]
    
    passed = 0
    total = len(tests)
    
    for test_name, test_func in tests:
        try:
            if test_func():
                passed += 1
        except Exception as e:
            print(f"❌ {test_name} 테스트 중 예외 발생: {e}")
    
    print(f"\n🏁 테스트 완료: {passed}/{total} 통과")
    
    if passed == total:
        print("🎉 모든 테스트가 성공했습니다!")
        return True
    else:
        print("⚠️  일부 테스트가 실패했습니다.")
        return False


if __name__ == "__main__":
    main() 