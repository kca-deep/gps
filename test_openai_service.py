#!/usr/bin/env python3
"""
OpenAI 서비스 및 채팅 기능 테스트
"""

import os
import sys
import time
import logging
from datetime import datetime

# 프로젝트 루트 디렉토리를 Python 경로에 추가
project_root = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, project_root)

from src.gps_inspection.services.openai_service import OpenAIService, ChatContext
from src.gps_inspection.models.database import DatabaseManager
from src.gps_inspection.models.wireless_station import WirelessStationDAO

# 로깅 설정
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def test_openai_service():
    """OpenAI 서비스 기본 기능 테스트"""
    print("🧪 OpenAI 서비스 테스트 시작")
    print("=" * 50)
    
    # 서비스 초기화
    service = OpenAIService()
    
    # 1. 서비스 상태 확인
    print(f"✅ OpenAI 클라이언트 사용 가능: {service.client_available}")
    print(f"✅ API 키 설정: {'Yes' if service.api_key else 'No (모의 모드)'}")
    
    # 2. 채팅 컨텍스트 생성
    context = ChatContext(
        session_id="test_session_001",
        user_location={
            'latitude': 37.5665,  # 서울시청
            'longitude': 126.9780
        }
    )
    
    print(f"✅ 채팅 컨텍스트 생성: {context.session_id}")
    
    # 3. 다양한 메시지 테스트
    test_messages = [
        "안녕하세요",
        "무선국 검색",
        "서울 무선국 찾아줘",
        "근처 무선국 조회",
        "새로운 무선국 등록",
        "무선국 목록 보여줘",
        "도움말"
    ]
    
    for i, message in enumerate(test_messages, 1):
        print(f"\n🔸 테스트 {i}: '{message}'")
        try:
            start_time = time.time()
            response = service.process_message(message, context)
            elapsed_time = time.time() - start_time
            
            print(f"   응답 시간: {elapsed_time:.2f}초")
            print(f"   응답: {response['response'][:100]}...")
            print(f"   액션 개수: {len(response.get('actions', []))}")
            print(f"   데이터 포함: {'Yes' if response.get('data') else 'No'}")
            
        except Exception as e:
            print(f"   ❌ 오류: {e}")
    
    # 4. 빠른 액션 테스트
    print(f"\n🔸 빠른 액션 테스트")
    quick_actions = service.get_quick_actions(context)
    for action in quick_actions:
        print(f"   - {action['text']}: {action['action']}")
    
    # 5. 캐시 성능 테스트
    print(f"\n🔸 캐시 성능 테스트")
    message = "테스트 메시지"
    
    # 첫 번째 호출 (캐시 없음)
    start_time = time.time()
    service.process_message(message, context)
    first_call_time = time.time() - start_time
    
    # 두 번째 호출 (캐시 사용)
    start_time = time.time()
    service.process_message(message, context)
    second_call_time = time.time() - start_time
    
    print(f"   첫 번째 호출: {first_call_time:.3f}초")
    print(f"   두 번째 호출: {second_call_time:.3f}초")
    if second_call_time > 0:
        print(f"   캐시 성능 향상: {first_call_time/second_call_time:.1f}배")
    
    print("\n✅ OpenAI 서비스 테스트 완료")

def test_database_integration():
    """데이터베이스 연동 테스트"""
    print("\n🧪 데이터베이스 연동 테스트 시작")
    print("=" * 50)
    
    try:
        # 데이터베이스 초기화
        db_manager = DatabaseManager()
        dao = WirelessStationDAO()
        
        print("✅ 데이터베이스 연결 성공")
        
        # 테스트 데이터 조회
        stations, total = dao.get_all_stations(limit=5)
        print(f"✅ 무선국 데이터 조회: {total}개 중 {len(stations)}개 표시")
        
        for station in stations:
            print(f"   - {station.station_name} ({station.latitude}, {station.longitude})")
        
    except Exception as e:
        print(f"❌ 데이터베이스 연동 오류: {e}")
    
    print("✅ 데이터베이스 연동 테스트 완료")

def test_full_chat_scenario():
    """전체 채팅 시나리오 테스트"""
    print("\n🧪 전체 채팅 시나리오 테스트 시작")
    print("=" * 50)
    
    service = OpenAIService()
    context = ChatContext(
        session_id="scenario_test",
        user_location={
            'latitude': 35.1595,  # 부산시청
            'longitude': 129.0756
        }
    )
    
    # 시나리오: 사용자가 무선국을 검색하고 근처 조회 후 등록하는 과정
    scenario_messages = [
        "안녕하세요, 무선국 검사를 도와주세요",
        "부산 무선국을 찾고 싶어요",
        "현재 위치 근처에 무선국이 있나요?",
        "새로운 무선국을 등록하고 싶습니다",
        "등록 절차를 알려주세요"
    ]
    
    print("📱 채팅 시나리오 시뮬레이션:")
    print("=" * 30)
    
    for i, message in enumerate(scenario_messages, 1):
        print(f"\n👤 사용자: {message}")
        
        try:
            response = service.process_message(message, context)
            print(f"🤖 AI: {response['response']}")
            
            if response.get('actions'):
                print(f"🔘 제안 액션: {', '.join([a.get('text', a.get('action', '')) for a in response['actions'][:3]])}")
                
        except Exception as e:
            print(f"❌ 오류: {e}")
        
        time.sleep(1)  # 자연스러운 대화 흐름을 위한 지연
    
    print("\n✅ 전체 채팅 시나리오 테스트 완료")

def test_performance():
    """성능 테스트"""
    print("\n🧪 성능 테스트 시작")
    print("=" * 50)
    
    service = OpenAIService()
    
    # 다중 세션 동시 처리 테스트
    contexts = []
    for i in range(5):
        context = ChatContext(
            session_id=f"perf_test_{i}",
            user_location={
                'latitude': 37.5665 + (i * 0.01),
                'longitude': 126.9780 + (i * 0.01)
            }
        )
        contexts.append(context)
    
    print("🔸 다중 세션 동시 처리 테스트")
    
    start_time = time.time()
    for i, context in enumerate(contexts):
        message = f"테스트 메시지 {i+1}"
        try:
            response = service.process_message(message, context)
            print(f"   세션 {i+1}: ✅ 성공")
        except Exception as e:
            print(f"   세션 {i+1}: ❌ 실패 - {e}")
    
    total_time = time.time() - start_time
    print(f"   총 처리 시간: {total_time:.2f}초")
    print(f"   평균 응답 시간: {total_time/len(contexts):.2f}초")
    
    print("\n✅ 성능 테스트 완료")

def main():
    """메인 테스트 실행"""
    print("🚀 GPS 무선국 검사 AI 채팅 시스템 통합 테스트")
    print(f"📅 테스트 시작 시간: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)
    
    try:
        # 1. OpenAI 서비스 기본 테스트
        test_openai_service()
        
        # 2. 데이터베이스 연동 테스트
        test_database_integration()
        
        # 3. 전체 채팅 시나리오 테스트
        test_full_chat_scenario()
        
        # 4. 성능 테스트
        test_performance()
        
        print("\n" + "=" * 60)
        print("🎉 모든 테스트가 완료되었습니다!")
        print("💡 웹 브라우저에서 http://127.0.0.1:5000/chat 에 접속해서 UI를 테스트해보세요.")
        
    except Exception as e:
        print(f"\n❌ 테스트 실행 중 치명적 오류: {e}")
        import traceback
        traceback.print_exc()
    
    print(f"\n📅 테스트 종료 시간: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

if __name__ == '__main__':
    main() 