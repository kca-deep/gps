"""
한국어 처리 유틸리티

초성 추출, 편집거리 계산, 한국어 텍스트 정규화 등의 기능 제공
외부 라이브러리 의존성 없이 기본적인 한국어 처리 구현
"""

import re
from typing import List, Optional


class KoreanUtils:
    """한국어 처리 유틸리티 클래스"""
    
    # 한국어 초성 리스트
    CHOSUNG_LIST = [
        'ㄱ', 'ㄲ', 'ㄴ', 'ㄷ', 'ㄸ', 'ㄹ', 'ㅁ', 'ㅂ', 'ㅃ', 'ㅅ',
        'ㅆ', 'ㅇ', 'ㅈ', 'ㅉ', 'ㅊ', 'ㅋ', 'ㅌ', 'ㅍ', 'ㅎ'
    ]
    
    # 한국어 중성 리스트
    JUNGSUNG_LIST = [
        'ㅏ', 'ㅐ', 'ㅑ', 'ㅒ', 'ㅓ', 'ㅔ', 'ㅕ', 'ㅖ', 'ㅗ', 'ㅘ',
        'ㅙ', 'ㅚ', 'ㅛ', 'ㅜ', 'ㅝ', 'ㅞ', 'ㅟ', 'ㅠ', 'ㅡ', 'ㅢ', 'ㅣ'
    ]
    
    # 한국어 종성 리스트
    JONGSUNG_LIST = [
        '', 'ㄱ', 'ㄲ', 'ㄳ', 'ㄴ', 'ㄵ', 'ㄶ', 'ㄷ', 'ㄹ', 'ㄺ', 'ㄻ',
        'ㄼ', 'ㄽ', 'ㄾ', 'ㄿ', 'ㅀ', 'ㅁ', 'ㅂ', 'ㅄ', 'ㅅ', 'ㅆ', 'ㅇ',
        'ㅈ', 'ㅊ', 'ㅋ', 'ㅌ', 'ㅍ', 'ㅎ'
    ]
    
    def __init__(self):
        """한국어 유틸리티 초기화"""
        # 한글 범위: 가(44032) ~ 힣(55203)
        self.hangul_start = ord('가')
        self.hangul_end = ord('힣')
        
        # 초성만 있는 문자 범위: ㄱ(12593) ~ ㅎ(12622)
        self.chosung_start = ord('ㄱ')
        self.chosung_end = ord('ㅎ')
    
    def is_hangul(self, char: str) -> bool:
        """
        문자가 한글인지 확인
        
        Args:
            char: 확인할 문자
            
        Returns:
            한글 여부
        """
        if len(char) != 1:
            return False
        
        char_code = ord(char)
        return self.hangul_start <= char_code <= self.hangul_end
    
    def is_chosung_only(self, char: str) -> bool:
        """
        문자가 초성만 있는지 확인
        
        Args:
            char: 확인할 문자
            
        Returns:
            초성만 있는 문자 여부
        """
        if len(char) != 1:
            return False
        
        char_code = ord(char)
        return self.chosung_start <= char_code <= self.chosung_end
    
    def extract_chosung(self, text: str) -> str:
        """
        텍스트에서 초성 추출
        
        Args:
            text: 초성을 추출할 텍스트
            
        Returns:
            초성 문자열
        """
        chosung_result = []
        
        for char in text:
            if self.is_hangul(char):
                # 한글 문자의 초성 추출
                char_code = ord(char) - self.hangul_start
                chosung_index = char_code // (21 * 28)  # 21: 중성 개수, 28: 종성 개수
                chosung_result.append(self.CHOSUNG_LIST[chosung_index])
            elif self.is_chosung_only(char):
                # 이미 초성인 경우 그대로 추가
                chosung_result.append(char)
            elif char.isalnum():
                # 영문/숫자는 그대로 유지
                chosung_result.append(char)
        
        return ''.join(chosung_result)
    
    def is_chosung_query(self, query: str) -> bool:
        """
        쿼리가 초성 검색용인지 확인
        
        Args:
            query: 확인할 쿼리
            
        Returns:
            초성 쿼리 여부
        """
        if not query:
            return False
        
        # 모든 문자가 초성이거나 영문/숫자인 경우
        for char in query:
            if not (self.is_chosung_only(char) or char.isalnum() or char.isspace()):
                return False
        
        # 최소 하나의 초성이 포함되어야 함
        return any(self.is_chosung_only(char) for char in query)
    
    def normalize_text(self, text: str) -> str:
        """
        텍스트 정규화 (공백 정리, 특수문자 제거 등)
        
        Args:
            text: 정규화할 텍스트
            
        Returns:
            정규화된 텍스트
        """
        if not text:
            return ""
        
        # 연속된 공백을 하나로 정리
        normalized = re.sub(r'\s+', ' ', text.strip())
        
        # 특수문자 제거 (한글, 영문, 숫자, 공백만 유지)
        normalized = re.sub(r'[^\w\s가-힣]', '', normalized)
        
        return normalized
    
    def simple_edit_distance(self, s1: str, s2: str) -> int:
        """
        간단한 편집거리(Levenshtein distance) 계산
        
        Args:
            s1: 첫 번째 문자열
            s2: 두 번째 문자열
            
        Returns:
            편집거리
        """
        if not s1:
            return len(s2)
        if not s2:
            return len(s1)
        
        # 정규화
        s1 = self.normalize_text(s1.lower())
        s2 = self.normalize_text(s2.lower())
        
        # DP 테이블 생성
        len1, len2 = len(s1), len(s2)
        dp = [[0] * (len2 + 1) for _ in range(len1 + 1)]
        
        # 초기화
        for i in range(len1 + 1):
            dp[i][0] = i
        for j in range(len2 + 1):
            dp[0][j] = j
        
        # DP 계산
        for i in range(1, len1 + 1):
            for j in range(1, len2 + 1):
                if s1[i-1] == s2[j-1]:
                    dp[i][j] = dp[i-1][j-1]
                else:
                    dp[i][j] = min(
                        dp[i-1][j] + 1,      # 삭제
                        dp[i][j-1] + 1,      # 삽입
                        dp[i-1][j-1] + 1     # 교체
                    )
        
        return dp[len1][len2]
    
    def calculate_similarity(self, s1: str, s2: str) -> float:
        """
        두 문자열의 유사도 계산 (0~1)
        
        Args:
            s1: 첫 번째 문자열
            s2: 두 번째 문자열
            
        Returns:
            유사도 (0: 완전히 다름, 1: 완전히 같음)
        """
        if not s1 and not s2:
            return 1.0
        
        max_len = max(len(s1), len(s2))
        if max_len == 0:
            return 1.0
        
        edit_distance = self.simple_edit_distance(s1, s2)
        return 1.0 - (edit_distance / max_len)
    
    def extract_keywords(self, text: str) -> List[str]:
        """
        텍스트에서 키워드 추출
        
        Args:
            text: 키워드를 추출할 텍스트
            
        Returns:
            키워드 리스트
        """
        if not text:
            return []
        
        # 정규화
        normalized = self.normalize_text(text)
        
        # 공백 기준으로 분할
        words = normalized.split()
        
        # 너무 짧은 단어 제거
        keywords = [word for word in words if len(word) >= 2]
        
        return keywords
    
    def contains_hangul(self, text: str) -> bool:
        """
        텍스트에 한글이 포함되어 있는지 확인
        
        Args:
            text: 확인할 텍스트
            
        Returns:
            한글 포함 여부
        """
        return any(self.is_hangul(char) for char in text)
    
    def get_word_variations(self, word: str) -> List[str]:
        """
        단어의 변형들 생성 (검색 확장용)
        
        Args:
            word: 기준 단어
            
        Returns:
            변형 단어 리스트
        """
        variations = [word]
        
        # 초성 버전 추가
        if self.contains_hangul(word):
            chosung = self.extract_chosung(word)
            if chosung and chosung != word:
                variations.append(chosung)
        
        # 공통 변형 패턴
        common_replacements = {
            '센터': ['센타', '센터'],
            '센타': ['센터', '센타'],
            '빌딩': ['빌딩', '건물'],
            '타워': ['타워', '타와'],
            '스테이션': ['스테이션', '역'],
            '포트': ['포트', '항구', '항'],
        }
        
        for original, replacements in common_replacements.items():
            if original in word:
                for replacement in replacements:
                    new_word = word.replace(original, replacement)
                    if new_word not in variations:
                        variations.append(new_word)
        
        return variations 