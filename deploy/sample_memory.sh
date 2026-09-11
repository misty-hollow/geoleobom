#!/usr/bin/env bash
# 부하 중 서버 메모리·스왑을 1초 간격으로 기록한다 (v2.3 10절 게이트 2).
#
# 게이트 2의 통과 기준은 **부하 중 MemAvailable 약 1GB 이상**이고,
# "오류·OOM·지속적 스왑 I/O 없음"도 함께 본다. 그래서 세 가지를 같이 남긴다.
#
#   - MemAvailable (kB)      : /proc/meminfo
#   - 스왑 사용량 (kB)        : /proc/meminfo SwapFree 대비
#   - 스왑 I/O 누적 (pswpin/pswpout 페이지) : /proc/vmstat
#
# 스왑 "사용량"과 스왑 "I/O"는 다르다. 한 번 스왑에 올라간 페이지가 그대로 있는 것은
# 지속적 I/O가 아니다. 그래서 누적 카운터를 남겨 **증가 여부**를 보게 한다.
#
# 서버에서:
#   bash sample_memory.sh 180 > /tmp/mem.tsv    # 180초 동안
# 끝난 뒤:
#   bash sample_memory.sh --summary /tmp/mem.tsv

set -euo pipefail

if [[ "${1:-}" == "--summary" ]]; then
	FILE="${2:?usage: $0 --summary <file>}"
	awk -F'\t' '
		NR == 1 { next }
		{
			avail = $2
			if (min_avail == 0 || avail < min_avail) min_avail = avail
			swap_used = $3
			if (swap_used > max_swap) max_swap = swap_used
			if (NR == 2) { first_in = $4; first_out = $5 }
			last_in = $4; last_out = $5
			n++
		}
		END {
			printf "표본 %d개\n", n
			printf "MemAvailable 최솟값: %.0f MB\n", min_avail / 1024
			printf "스왑 사용 최댓값:    %.0f MB\n", max_swap / 1024
			printf "스왑 I/O 증가(in):   %d pages\n", last_in - first_in
			printf "스왑 I/O 증가(out):  %d pages\n", last_out - first_out
			printf "게이트 2 기준 MemAvailable 약 1GB(1024MB) 이상: %s\n", \
				(min_avail / 1024 >= 1024 ? "통과" : "미달")
		}
	' "$FILE"
	exit 0
fi

SECONDS_TO_RUN="${1:-120}"

printf 'epoch\tmem_available_kb\tswap_used_kb\tpswpin\tpswpout\n'
END=$((SECONDS + SECONDS_TO_RUN))
while [[ $SECONDS -lt $END ]]; do
	AVAIL=$(awk '/^MemAvailable:/ {print $2}' /proc/meminfo)
	SWAP_TOTAL=$(awk '/^SwapTotal:/ {print $2}' /proc/meminfo)
	SWAP_FREE=$(awk '/^SwapFree:/ {print $2}' /proc/meminfo)
	PSWPIN=$(awk '/^pswpin/ {print $2}' /proc/vmstat)
	PSWPOUT=$(awk '/^pswpout/ {print $2}' /proc/vmstat)
	printf '%s\t%s\t%s\t%s\t%s\n' "$(date +%s)" "$AVAIL" "$((SWAP_TOTAL - SWAP_FREE))" "$PSWPIN" "$PSWPOUT"
	sleep 1
done
