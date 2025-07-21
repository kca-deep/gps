#!/usr/bin/env python3
"""
서버 상태 및 채팅 API 테스트 스크립트
"""

import requests
import json
import time
from datetime import datetime

def test_server_health():
    """서버 헬스 체크"""
    try:
        response = requests.get('http://127.0.0.1:5000/health', timeout=5)
        print(f"🔍 헬스 체크: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            print(f"✅ 서버 상태: {data.get('status')}")
            print(f"📊 구성요소: {data.get('components', {})}")
            return True
        else:
            print(f"❌ 헬스 체크 실패: {response.text}")
            return False
            
    except Exception as e:
        print(f"❌ 서버 연결 실패: {e}")
        return False

def test_api_endpoints():
    """API 엔드포인트 테스트"""
    base_url = 'http://127.0.0.1:5000'
    
    endpoints = [
        ('GET', '/'),
        ('GET', '/health'),
        ('POST', '/api/chat/session'),
        ('GET', '/api/stations'),
        ('GET', '/api/search/stations?q=test')
    ]
    
    print("\n🧪 API 엔드포인트 테스트:")
    print("=" * 40)
    
    for method, endpoint in endpoints:
        try:
            if method == 'GET':
                response = requests.get(f"{base_url}{endpoint}", timeout=5)
            elif method == 'POST':
                response = requests.post(f"{base_url}{endpoint}", 
                                       json={}, timeout=5)
            
            status = "✅" if 200 <= response.status_code < 400 else "❌"
            print(f"{status} {method} {endpoint}: {response.status_code}")
            
        except Exception as e:
            print(f"❌ {method} {endpoint}: {e}")

def test_chat_session():
    """채팅 세션 테스트"""
    base_url = 'http://127.0.0.1:5000/api/chat'
    
    print("\n💬 채팅 세션 테스트:")
    print("=" * 40)
    
    try:
        # 1. 세션 생성
        session_data = {
            "location": {
                "latitude": 37.5665,
                "longitude": 126.9780
            }
        }
        
        response = requests.post(f"{base_url}/session", json=session_data, timeout=10)
        
        if response.status_code == 200:
            session_info = response.json()
            session_id = session_info.get('session_id')
            print(f"✅ 세션 생성 성공: {session_id}")
            print(f"📝 환영 메시지: {session_info.get('message', '')[:100]}...")
            
            # 2. 메시지 전송 테스트
            test_messages = [
                "안녕하세요",
                "무선국 검색",
                "도움말"
            ]
            
            for message in test_messages:
                print(f"\n👤 사용자: {message}")
                
                msg_data = {
                    "session_id": session_id,
                    "message": message,
                    "location": session_data["location"]
                }
                
                response = requests.post(f"{base_url}/message", json=msg_data, timeout=10)
                
                if response.status_code == 200:
                    result = response.json()
                    ai_response = result.get('response', '')
                    actions = result.get('actions', [])
                    
                    print(f"🤖 AI: {ai_response[:100]}...")
                    if actions:
                        print(f"🔘 액션: {len(actions)}개")
                    
                else:
                    print(f"❌ 메시지 전송 실패: {response.status_code}")
                
                time.sleep(1)  # API 호출 간격
            
            return True
            
        else:
            print(f"❌ 세션 생성 실패: {response.status_code}")
            print(f"   응답: {response.text}")
            return False
            
    except Exception as e:
        print(f"❌ 채팅 테스트 실패: {e}")
        return False

def test_web_ui():
    """웹 UI 접근 테스트"""
    try:
        response = requests.get('http://127.0.0.1:5000/chat', timeout=5)
        
        if response.status_code == 200:
            print(f"✅ 채팅 UI 접근 가능: http://127.0.0.1:5000/chat")
            print(f"📄 HTML 크기: {len(response.text)} bytes")
            
            # HTML에 기본 요소들이 있는지 확인
            html = response.text
            checks = [
                ('타이틀', 'GPS 무선국 검사 AI 채팅' in html),
                ('채팅 컨테이너', 'chat-container' in html),
                ('메시지 입력', 'message-input' in html),
                ('전송 버튼', 'send-btn' in html)
            ]
            
            for name, check in checks:
                status = "✅" if check else "❌"
                print(f"  {status} {name}")
            
            return True
        else:
            print(f"❌ 채팅 UI 접근 실패: {response.status_code}")
            return False
            
    except Exception as e:
        print(f"❌ 웹 UI 테스트 실패: {e}")
        return False

def main():
    """메인 테스트 실행"""
    print("🚀 GPS 무선국 검사 AI 채팅 시스템 서버 테스트")
    print(f"📅 테스트 시간: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)
    
    # 1. 서버 헬스 체크
    if not test_server_health():
        print("\n❌ 서버가 실행되지 않았습니다. 먼저 'python app.py'로 서버를 시작하세요.")
        return
    
    # 2. API 엔드포인트 테스트
    test_api_endpoints()
    
    # 3. 채팅 세션 테스트
    test_chat_session()
    
    # 4. 웹 UI 테스트
    print("\n🌐 웹 UI 테스트:")
    print("=" * 40)
    test_web_ui()
    
    print("\n" + "=" * 60)
    print("🎉 테스트 완료!")
    print("💡 웹 브라우저에서 http://127.0.0.1:5000/chat 에 접속해서 채팅을 테스트해보세요.")
    print("🔧 API 테스트: http://127.0.0.1:5000/ 에서 전체 시스템 정보를 확인할 수 있습니다.")

if __name__ == '__main__':
    main() 