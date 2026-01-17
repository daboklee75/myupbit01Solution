# Docker 기반 다중 봇 배포 가이드

Docker를 사용하면 복잡한 환경 설정 없이 깔끔하게 여러 개의 봇을 실행할 수 있습니다.

## 1. 사전 준비 (AWS t2.micro 필수 설정)

t2.micro는 램이 1GB밖에 없어서 Docker를 여러 개 돌리면 멈출 수 있습니다. **Swap 메모리(가상 램)**를 설정해야 안전합니다.

### Swap 메모리 설정 (2GB 추가)
터미널에 아래 명령어들을 한 줄씩 복사해서 붙여넣으세요.

```bash
# 1. 2GB Swap 파일 생성
sudo fallocate -l 2G /swapfile

# 2. 권한 설정
sudo chmod 600 /swapfile

# 3. Swap 영역 지정
sudo mkswap /swapfile

# 4. Swap 활성화
sudo swapon /swapfile

# 5. 재부팅 해도 유지되도록 설정
echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab

# 6. 확인 (Swp 항목이 2.0G로 나오면 성공)
free -h
```

---

## 2. Docker 설치

```bash
# 1. 설치 스크립트 실행
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh

# 2. 권한 부여 (중요)
sudo usermod -aG docker $USER

# 3. 적용을 위해 로그아웃 후 재접속
exit
# (다시 SSH 접속하세요)
```

---

## 3. 봇 실행하기 (다중 실행)

Docker Compose를 사용하면 설정 파일 하나로 여러 봇을 관리할 수 있습니다.

### 1단계: 사용자별 폴더 및 설정 준비
프로젝트 폴더(`myupbit01Solution`) 안에서 각 사용자별 폴더를 만듭니다.

```bash
# 내 폴더 만들기
mkdir -p users/me
cp .env users/me/.env 
# (혹은 nano users/me/.env 로 직접 수정)

# 친구 폴더 만들기
mkdir -p users/friend
cp .env.template users/friend/.env
nano users/friend/.env  
# (친구의 API KEY, 아이디/비번 입력)
```

### 2단계: 실행 (백그라운드)
```bash
docker compose up -d --build
```

### 3단계: 접속 확인
*   내 봇: `http://[서버IP]:8501`
*   친구 봇: `http://[서버IP]:8502`
    *   **주의**: AWS 보안 그룹(Security Group)에서 **8502** 포트가 열려 있어야 접속됩니다.

---

## 4. 관리 명령어

*   **상태 확인**: `docker compose ps`
*   **자원 확인**: `docker stats` (메모리 얼마나 먹는지 확인)
*   **전체 로그 보기**: `docker compose logs -f`
*   **특정 봇 로그 보기**: `docker compose logs -f my_bot`
*   **전체 종료**: `docker compose down`

---

## 5. Docker 사용의 장단점

### 장점 (Pros)
1.  **완전한 격리**: 여러 봇을 돌려도 서로의 라이브러리나 설정이 전혀 꼬이지 않습니다. (가장 큰 장점)
2.  **간편한 관리**: `docker-compose.yml` 파일 하나로 여러 봇을 한눈에 보고 켜고 끌 수 있습니다.
3.  **환경 일치**: 제 PC에서 잘 되면 서버에서도 무조건 잘 됩니다. ("제 컴퓨터에선 되는데요?" 문제 해결)

### 단점 (Cons)
1.  **리소스 소모**: 가상화 방식이므로 쌩으로 돌리는 것보다 메모리와 CPU를 아주 약간 더 씁니다. (t2.micro에서는 Swap 설정 없이는 2개 이상 구동 불가)
2.  **초기 설정**: Docker를 처음 설치하고 배우는 과정이 조금 낯설 수 있습니다.
