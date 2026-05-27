# Biophysical Skin Renderer + ICA Chromophore Decomposition

생물광학(biophysical) 기반 피부 렌더링 실험 도구입니다. 피부 albedo를 **기질(substrate) · 멜라닌 · 헤모글로빈** 세 성분으로 분리(ICA decomposition)하고, 그 맵들을 광학밀도(optical density) 도메인에서 재합성해 멜라닌/헤모글로빈 양을 인터랙티브하게 조절합니다.

## ▶ 바로 실행 (Live Demo)

설치·클론 없이 브라우저에서 바로 실행:

- **논문 버전**: <https://jin02.github.io/biophysical-skin-renderer-simulator/>
- **개량 버전(v2, 편집 가능한 Base Color)**: <https://jin02.github.io/biophysical-skin-renderer-simulator/skin-renderer-v2.html>

> 미러(빌드 불필요, CDN): <https://raw.githack.com/Jin02/biophysical-skin-renderer-simulator/main/skin-renderer.html>

| 파일 | 역할 |
|---|---|
| `skin_decompose.py` | 오프라인 **ICA 크로모포어 분해 도구** (논문 버전; albedo → substrate/melanin/hemoglobin) |
| `skin-renderer.html` | 브라우저 **시뮬레이터 위젯** (논문 버전, 의존성 없음) |
| `skin_decompose_v2.py` | **개량 분해기** — substrate를 추가로 `base color + grayscale`로 분리 |
| `skin-renderer-v2.html` | **개량 위젯** — base color를 직접 편집 가능 |
| `decompose.bat` | 임의 사진을 끌어다 놓으면 v2 분해 후 프리셋으로 등록 (Windows) |
| `skin_presets/`, `skin_presets_v2/` | 예제 텍스처 5종 + `manifest.json` (각 버전용) |
| `test_albedo.png` | 합성 예제 입력 albedo |

> 동봉된 텍스처는 알고리즘 시연용 **합성(synthetic)** 이미지입니다. 실제 결과를 보려면 자신의 albedo로 분해해 보세요(아래 "내 사진으로 해보기").

---

## 요구사항

- Python 3.9+
- `numpy`, `pillow`

```bash
pip install -r requirements.txt
```

---

## 1) ICA 분해 도구 — `skin_decompose.py`

피부 albedo 한 장을 광학밀도 도메인에서 **FastICA**로 분해해 멜라닌·헤모글로빈 농도 맵과 각 색소의 RGB 밀도 방향 벡터(`a_m`, `a_h`)를 추출합니다. 핵심 성질: `substrate = D − (c_m·a_m + c_h·a_h)` 로 정의하므로 scale 1에서 **원본 albedo가 정확히 복원**됩니다(ICA 품질과 무관하게 자기일관).

```bash
# 알고리즘 자체 검증 (합성 known-source 대비 cosine/correlation/round-trip)
python skin_decompose.py selftest

# 합성 예제 albedo 생성
python skin_decompose.py demo test_albedo.png

# albedo 1장 분해 -> OUTDIR/{substrate,melanin,hemoglobin}.png + decomp.json
python skin_decompose.py decompose  IN.png  OUTDIR  [--remove-shading]

# 예제 텍스처 5종 + manifest 생성 (위젯이 읽는 형식)
python skin_decompose.py presets  [ROOT]            # 기본 ROOT = skin_presets

# 내 이미지를 분해해 위젯 프리셋으로 등록
python skin_decompose.py add  IN.png  "Label"  [ROOT]  [--remove-shading]
```

**출력물**
- `substrate.png` — 색소가 제거된 기질 albedo (sRGB)
- `melanin.png`, `hemoglobin.png` — 농도 맵 (8-bit, **128 = 0**)
- `decomp.json` — `a_m`, `a_h`(밀도 방향), `m_scale`/`h_scale`(맵 인코딩 스케일), `gamma`

> `--remove-shading`: 깨끗한 albedo가 아니라 **음영이 들어간 사진**을 넣을 때 사용 (광학밀도에서 휘도 방향 (1,1,1)을 제거).

---

## 2) 시뮬레이터 위젯 — `skin-renderer.html`

정적 파일이지만 맵을 `fetch` 하므로 **로컬 서버**가 필요합니다(외부 CDN 의존성 없음).

```bash
python -m http.server 8123
# 브라우저에서 http://localhost:8123/skin-renderer.html
```

**조작**
- **Texture** 버튼 — 분해된 텍스처 세트 전환 (썸네일은 `skin_presets/<id>/albedo.png`)
- **Tone** 프리셋 — 흑인(VI)/백인(II)/황인(IV)/Original (Melanin·Hemoglobin Scale 세팅)
- **Melanin Scale / Hemoglobin Scale** — 각 색소량(기본 1 = 원본). 1보다 키우면 해당 색소를 더 입히고, 줄이면 뺍니다.
- 하단 썸네일 — 현재 텍스처의 substrate / melanin / hemoglobin 맵

---

## 3) 개량 버전 (v2) — 편집 가능한 Base Color

논문 버전은 그대로 두고, `skin_decompose_v2.py` + `skin-renderer-v2.html`을 별도로 추가했습니다.

**ICA 출력 = 4개**: `baseColor` + `grayscale` + `melanin` + `hemoglobin`.
substrate(색소 제거된 기질)를 **단일 base color + 회색 디테일(grayscale)** 로 한 번 더 분리하고, 둘은 **포토샵 Overlay 블렌드**로 합성합니다(grayscale은 중립값 0.5로 센터링되어 저장):

```
substrate_disp = Overlay(base_color, grayscale)   # 디스플레이 [0,1], 채널별
                                                  # grayscale=0.5 -> base_color (중립)
```

→ 위젯에서 **Base Color를 직접 편집**해 기본 스킨톤을 자유롭게 바꿀 수 있습니다(범용 커스텀). grayscale은 모공·구조 같은 디테일을 Overlay로 얹어 대비를 살립니다. 멜라닌을 빼서 창백하게 만들 때 생기던 마젠타 문제 없이 톤을 마음대로 조정할 수 있는 게 장점입니다.

버튼 행 구성:
- **Texture** — 선택한 텍스처에서 4개 맵(base/detail/melanin/hemoglobin)을 모두 로드.
- **Melanin / Hemoglobin** — 색소 맵만 다른 텍스처에서 골라 **조합**(짝이 되는 흡수 방향·스케일도 함께 따라옴). grayscale·base는 Texture에서 유지. 단 해상도가 같아야 함(동봉 프리셋 모두 256×256).
- **Skin** — Original·흑인·백인·황인 + 동아시아·동남아시아·남아시아·중동·라티노. base color + 색소 scale을 한 번에 세팅(`baseColor` 없는 프리셋은 텍스처 고유 색 사용).
- **MST** — **Monk Skin Tone** 1–10 (아래 설명).

### Monk Skin Tone (MST) 스케일

**Monk Skin Tone(MST)** 은 사회학자 Ellis Monk가 Google과 함께 2022년 공개한 **10단계 피부톤 스케일**입니다. 기존 **Fitzpatrick(I–VI, UV 반응 기반 6단계)** 이 특히 어두운 피부를 충분히 구분하지 못한다는 한계를 보완해, **더 포용적이고 색(hex)이 명확히 정의**된 것이 특징입니다 — 그래서 "더 검은/덜 검은"을 임의로 정하지 않고 **번호 + hex**로 객관적으로 표기할 수 있습니다.

| 단계 | hex | 단계 | hex |
|---|---|---|---|
| MST 1 | `#f6ede4` | MST 6  | `#a07e56` |
| MST 2 | `#f3e7db` | MST 7  | `#825c43` |
| MST 3 | `#f7ead0` | MST 8  | `#604134` |
| MST 4 | `#eadaba` | MST 9  | `#3a312a` |
| MST 5 | `#d7bd96` | MST 10 | `#292420` |

이 위젯은 각 MST 값을 **base color**(scale 1.0)로 사용합니다. 어두운 피부 범위는 대략 **MST 7–10** (예: deep skin ≈ MST 9 `#3a312a`). 참고: <https://skintone.google/>.

```bash
python skin_decompose_v2.py presets               # skin_presets_v2/ 생성 (5종)
python -m http.server 8123
# http://localhost:8123/skin-renderer-v2.html
```

자체 검증: `python skin_decompose_v2.py selftest` (Overlay(base, grayscale) substrate 재구성 오차 8-bit ~1).

---

## 내 사진으로 텍스처 만들기 (코드 몰라도 OK)

사진을 **`decompose.bat` 위에 끌어다 놓기**만 하면, 그 얼굴이 자동으로 분리되어 위젯에 새 텍스처로 추가됩니다. 명령어 입력 필요 없습니다.

### 1단계 — 처음 한 번만 준비
1. **Python 설치**: [python.org/downloads](https://www.python.org/downloads/) 에서 받아 설치.
   ⚠️ 설치 첫 화면의 **"Add Python to PATH"** 체크박스를 **반드시 켜세요**.
2. 이 폴더의 **`install.bat` 더블클릭** → 필요한 라이브러리가 자동 설치됩니다. 검은 창에 "Done"이 뜨면 끝.

### 2단계 — 사진 넣기 (매번)
1. 얼굴 사진(jpg/png)을 **`decompose.bat` 아이콘 위로 드래그&드롭**.
2. 검은 창이 뜨고 잠깐 뒤 **"Done…"** 메시지가 나옵니다. 아무 키나 누르면 닫혀요.

### 3단계 — 위젯에서 보기
1. **`serve.bat` 더블클릭** → 브라우저가 열립니다 (안 열리면 <http://localhost:8123/skin-renderer-v2.html> 직접 접속).
2. **Texture 줄에 방금 그 사진 버튼**이 생겨 있습니다. 누르고 슬라이더로 톤을 조절하세요!
   (이미 열려 있었다면 **새로고침**.)

> 💡 검은 창이 멈춰 있는 건 정상이에요(결과 보라고 일부러 멈춤). 서버 창은 위젯 쓰는 동안 켜둔 채로 두세요.
> 💡 **정면 + 균일한 조명** 사진일수록 결과가 깔끔합니다.

### 잘 안 될 때
| 증상 | 해결 |
|---|---|
| "Windows의 PC를 보호했습니다" 경고 | **추가 정보 → 실행**. (이 .bat은 짧은 텍스트 스크립트라 안전합니다) |
| 창이 깜빡하고 바로 닫힘 / "python을 찾을 수 없습니다" | Python이 없거나 PATH 미설정 → **Python 재설치 + "Add Python to PATH" 체크** |
| Texture 줄에 안 보임 | 위젯을 **새로고침**. (그냥 html 더블클릭이 아니라 `serve.bat`으로 열어야 함) |
| 그늘진 사진이라 색이 이상함 | 정면·균일조명 사진을 쓰거나, 아래 advanced의 `--remove-shading` 사용 |

> 내 PC에서 추가한 텍스처는 **내 컴퓨터에서만** 보입니다. 공유 사이트(github.io)에도 올리려면 개발자에게 `skin_presets_v2` 폴더를 commit/push 해달라고 하세요.

<details><summary>명령창에 익숙한 분 (advanced)</summary>

```bash
python skin_decompose_v2.py add  my_face.png  "My Face"                 # 분해 + 위젯에 등록
python skin_decompose_v2.py add  photo.jpg "Photo" skin_presets_v2 --remove-shading  # 음영 사진
python skin_decompose_v2.py decompose  test_albedo.png  out            # 4개 출력만 폴더로 (검사용)
python skin_decompose_v2.py selftest                                    # 분해 정확도 출력
python -m http.server 8123                                              # 위젯 서버
```
분해 출력 4개 = `decomp.json`(여기에 `baseColor`) + `grayscale.png` + `melanin.png` + `hemoglobin.png`.
</details>

---

## 동작 원리 (수식)

광학밀도(자연로그) 도메인에서 픽셀별로:

```
Moff = MEL_GAIN*(Mscale-1);  Hoff = HEM_GAIN*(Hscale-1)
D_out = D_substrate + Mscale*c_m*a_m + Hscale*c_h*a_h + Moff*MEL_DIR + Hoff*HEM_DIR
albedo = exp(-D_out) ^ (1/gamma)
```

- `D_substrate = -ln(linear(substrate))`
- `c_m`, `c_h` — 분해된 농도 맵 (decode: `(pixel*255 - 128) / scale`)
- `a_m`, `a_h` — 텍스처 고유 ICA 밀도 방향 (공간적 주근깨/홍조 변동)
- `MEL_DIR`, `HEM_DIR` — 정준 발색단 방향(전역 톤 리톤용). 색소 맵은 zero-mean(변동만)이라, 전체 톤을 바꾸려면 균일 오프셋을 함께 더합니다.
- scale 1,1 → 오프셋 0 → 원본 정확 복원

---

## 설계 노트 (Design Notes)

작업하며 내린 주요 결정과 그 근거입니다.

### A. 물리 모델 근거
- **감산(subtractive) 혼합 / 변형 Beer–Lambert**: 발색단은 빛을 *흡수*하므로 광학밀도 도메인에서 더해지고(`D = Σ cᵢ·kᵢ`), 반사율 = `exp(−D)`. 색이 더해지는 게 아니라 base에서 깎여 나갑니다.
- **유/페오는 독립이 아니라 Amount+Blend**: 유멜라닌·페오멜라닌은 같은 멜라노좀의 *유한한 부피 분율*을 나눠 가집니다. 둘을 독립 슬라이더로 두면 합이 상한을 넘는 비물리 상태가 가능(부피/에너지 보존 위반). 물리적으로 올바른 제어는 총량(Amount)+비율(Blend) → 이 위젯이 독립 eu/pheo 스케일을 두지 않는 이유.
- **흡수 계수는 근사값**: `MELANIN_ABSORB` 등은 문헌 스펙트럼을 RGB로 근사·튜닝한 예시값이며 특정 논문 수치 그대로가 아닙니다.

### B. ICA 분해 결정
- **블라인드 ICA vs 고정 기저**: FastICA(블라인드)로 색소 축을 추정합니다. 대안인 "고정 기저 투영"은 순방향 모델의 *정확한 역*이라 재현성이 높지만 사진 적응성이 낮아, 임의 사진 대응을 위해 ICA를 택했습니다.
- **substrate 자기일관성**: `substrate = D_원본 − (색소 기여)`로 정의 → scale 1에서 **ICA 품질과 무관하게 원본이 정확히 복원**됩니다(ICA는 "변동을 어떻게 나눌지"만 결정).
- **라벨링 휴리스틱**: 추출된 두 축 중 *정규화 후 청색 분율이 큰 쪽*을 멜라닌으로 판정. (초기엔 정규화 안 한 raw 성분으로 비교해 라벨이 뒤바뀌는 버그가 있었음 — 벡터 크기 차이 때문.)
- **셰이딩 제거(`--remove-shading`)**: 광학밀도에서 휘도 방향 `(1,1,1)`을 제거. 음영과 멜라닌의 휘도 성분이 같은 방향이라 완벽 분리는 불가 → 깨끗한 albedo면 끄고, 음영 사진이면 켭니다.
- **ICA 전제**: 색소 분포가 *공간적으로 독립 + 비가우시안*이어야 잘 분리됩니다(동봉 합성 텍스처가 sparse한 주근깨·홍조를 쓰는 이유).

### C. 톤·색 제어 결정 (v2)
- **baseColor가 주 톤 컨트롤**: baseColor는 이미 "평균 멜라닌+헤모글로빈의 결과 색"이라 톤은 색을 직접 고르는 게 가장 정확. 그래서 독립 eu/pheo 스케일은 추가하지 않음(에너지 보존 + baseColor와 중복).
- **마젠타 문제**: 멜라닌을 빼서 창백하게 만들려 하면 청색 흡수가 줄어 **청색이 녹색을 추월**해 피부가 마젠타로 뜹니다. 한때 중립 Lightness 항으로 우회했으나, 결국 **baseColor 직접 편집**으로 정리(마젠타 없음). Lightness는 제거.
- **multiply → Overlay**: 처음엔 `substrate = grayscale × baseColor`(곱)였으나 포토샵식 **Overlay**로 바꿔 디테일 대비를 살림. Overlay가 의미 있도록 grayscale을 **중립 0.5로 센터링**해 저장.
- **RGB tint 제거(v2)**: baseColor와 RGB tint는 둘 다 "전역 per-channel 색 곱"이라 수학적으로 중복. 풀 컬러 피커인 baseColor가 tint를 포함하므로 v2에선 제거(v1은 baseColor가 없어 유지).

### D. 피부톤 표준 비교
| 표준 | 비고 |
|---|---|
| **Monk Skin Tone (MST)** | 10단계, 정의된 hex, 포용성 — 본 위젯 채택 |
| Fitzpatrick I–VI | 피부과 표준, UV 반응 기반(색 아님), 어두운 톤 구분 약함 |
| Pantone SkinTone | 상업용 110 스와치(유료) |
| ITA° | CIELAB 기반 측정식 분류(연구/화장품) |

---

## 알려진 한계

- 동봉 텍스처는 **합성**입니다. 실제 스캔 albedo로 분해하면 분리 품질을 제대로 확인할 수 있습니다.
- 이미 밝은 기질에서는 "백인"을 더 창백하게 만들기 어렵습니다 — 멜라닌을 더 빼면 청색이 녹색을 추월해 마젠타로 떠버립니다(멜라닌 청색 흡수가 큼). 어두운 텍스처에서는 멜라닌 감소가 실제로 톤을 밝힙니다. 어떤 텍스처에서도 균일하게 밝히려면 density에서 상수를 빼는 "lightness" 항을 추가하면 됩니다.
- ICA는 입력의 비가우시안성·독립성에 의존합니다. 균일조명 정면 얼굴에서 가장 안정적입니다.

---

## 참고 문헌 (References)

이 프로젝트가 기반한 문헌과, 각 문헌에서 **무엇을 가져왔는지**:

1. **Tsumura, Haneishi, Miyake (1999)** — *"Independent-component analysis of skin color image"*, JOSA A 16(9): 2169–2176.
   → `skin_decompose.py`의 직접적 근거. 광학밀도(optical density) 도메인에서 **ICA로 멜라닌·헤모글로빈을 분리**한다는 핵심 아이디어와 가정(두 색소가 공간적으로 독립, 밀도 도메인에서 선형 결합).
   <https://opg.optica.org/josaa/abstract.cfm?uri=josaa-16-9-2169>

2. **Tsumura, Ojima, et al. (2003)** — *"Image-based skin color and texture analysis/synthesis by extracting hemoglobin and melanin information in the skin"*, ACM SIGGRAPH 2003 / TOG 22(3): 770–779.
   → 분해된 색소를 다시 합성해 색을 바꾸는 **analysis/synthesis 파이프라인**. 위젯의 "맵 추출 → 농도 스케일 → 재합성" 흐름이 여기서 옴.

3. **Donner & Jensen (2006)** — *"A Spectral BSSRDF for Shading Human Skin"*, Eurographics Symposium on Rendering (EGSR) 2006.
   → 피부를 **(멜라닌 농도, eu/pheo blend, 헤모글로빈 농도, 산소포화도)** 로 매개화하는 생물광학 모델. 발색단 기반 파라미터화의 표준 근거.

4. **Donner, Weyrich, d'Eon, Ramamoorthi, Rusinkiewicz (2008)** — *"A Layered, Heterogeneous Reflectance Model for Acquiring and Rendering Human Skin"*, ACM SIGGRAPH Asia 2008 / TOG 27(5).
   → 표피/진피 **층상 모델**과 색소로부터 albedo를 구성하는 관점. `substrate × 색소 흡수` 구성의 배경.
   <https://gfx.cs.princeton.edu/pubs/Donner_2008_ALH/donner08hskin.pdf>

5. **Jacques (2013)** — *"Optical properties of biological tissues: a review"*, Physics in Medicine & Biology 58(11): R37–R61.
   → 멜라닌 흡수의 파장 의존성(대략 `μa ∝ λ^−3.46`, 단파장일수록 강하게 흡수). 유멜라닌 RGB 흡수 계수가 **청색 편향**을 갖는 형태의 근거.

6. **(survey)** *"Comparison of Methods in Skin Pigment Decomposition"* (2024), arXiv:2404.00552.
   → PCA/ICA 등 색소 분해 기법 비교. **고정 기저 투영 vs 블라인드 ICA** 선택을 참고.
   <https://arxiv.org/abs/2404.00552>

> **정직성 노트:** 코드의 흡수 계수 `float3`(`MEL_DIR=(1.20,2.34,4.20)`, `HEM_DIR=(0.25,1.80,1.20)` 등)와 게인(`MEL_GAIN`, `HEM_GAIN`)은 위 문헌의 분광 곡선을 RGB로 **근사·튜닝한 예시 상수**이며, 특정 논문의 수치를 그대로 옮긴 값이 아닙니다. 정량적 정확도가 필요하면 측정된 흡수 스펙트럼을 sRGB primary에 직접 적분해 교체하세요. ICA 분해 절차(밀도 변환·휘도 제거·FastICA)는 위 1·2번 문헌을 따릅니다.
