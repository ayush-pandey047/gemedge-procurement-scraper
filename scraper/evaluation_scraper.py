import asyncio
import logging
import re
from dataclasses import dataclass, field
from typing import Optional

import aiohttp
from bs4 import BeautifulSoup

from config.settings import (
    EVALUATION_URL,
    BASE_URL,
    ALL_BIDS_URL,
    NUM_DETAIL_WORKERS,
    REQUEST_TIMEOUT,
    RETRY_ATTEMPTS,
    RETRY_DELAY,
)

logger = logging.getLogger(__name__)


@dataclass
class VendorEntry:
    vendor_name: str = ""
    vendor_rank: str = ""       
    vendor_price: str = ""
    remarks: str = ""
    disqualified: bool = False


@dataclass
class EvaluationDetail:
    result_id: str = ""
    vendors: list[VendorEntry] = field(default_factory=list)
    accessible: bool = True
    error: str = ""


def _rank_label(rank_int: int) -> str:
    return f"L{rank_int}"


def _parse_evaluation_html(html: str, result_id: str) -> EvaluationDetail:
    """Parse evaluation page HTML into structured vendor entries."""
    detail = EvaluationDetail(result_id=result_id)
    soup = BeautifulSoup(html, "lxml")
    page_text = soup.get_text().lower()


    if any(kw in page_text for kw in ["please login", "sign in", "unauthorized", "sso"]):
        detail.accessible = False
        detail.error = "login_required"
        return detail


    tables = soup.select("table")
    eval_table = None
    for tbl in tables:
        hdr = " ".join(th.get_text(strip=True).lower() for th in tbl.select("th"))
        if any(kw in hdr for kw in ["rank", "vendor", "price", "l1", "l2", "disqualif"]):
            eval_table = tbl
            break

    if not eval_table:
        detail.error = "no_eval_table"
        return detail

    headers = [th.get_text(strip=True).lower() for th in eval_table.select("th")]
    rank_col = next((i for i, h in enumerate(headers) if "rank" in h), 0)
    vendor_col = next((i for i, h in enumerate(headers) if "vendor" in h or "name" in h or "firm" in h), 1)
    price_col = next((i for i, h in enumerate(headers) if "price" in h or "quoted" in h or "amount" in h), 2)
    status_col = next((i for i, h in enumerate(headers) if "status" in h or "disq" in h), -1)
    remarks_col = next((i for i, h in enumerate(headers) if "remark" in h or "note" in h), -1)

    rank_counter = 1
    for row in eval_table.select("tbody tr, tr"):
        cells = row.find_all("td")
        if not cells or len(cells) < 2:
            continue

        def cell(i):
            return cells[i].get_text(strip=True) if 0 <= i < len(cells) else ""

        vendor_name = cell(vendor_col)
        if not vendor_name:
            continue

        raw_rank = cell(rank_col)
        price = cell(price_col)
        status = cell(status_col) if status_col >= 0 else ""
        remarks = cell(remarks_col) if remarks_col >= 0 else ""

        is_dq = any(kw in (raw_rank + status + remarks).lower() for kw in ["disq", "dq", "rejected", "elimina"])

     
        if is_dq:
            rank_label = "DQ"
        elif raw_rank and re.match(r"[Ll]\d", raw_rank):
            rank_label = raw_rank.upper()
        elif raw_rank and raw_rank.isdigit():
            rank_label = _rank_label(int(raw_rank))
        else:
            rank_label = _rank_label(rank_counter) if not is_dq else "DQ"
            if not is_dq:
                rank_counter += 1

        entry = VendorEntry(
            vendor_name=vendor_name,
            vendor_rank=rank_label,
            vendor_price=price,
            remarks=remarks,
            disqualified=is_dq,
        )
        detail.vendors.append(entry)

    return detail


async def _fetch_evaluation(
    session: aiohttp.ClientSession,
    result_id: str,
    semaphore: asyncio.Semaphore,
) -> EvaluationDetail:
    """Try /getEvaluationDetails/{id} first, then fall back to the result page itself."""
    url = f"{EVALUATION_URL}/{result_id}"
    async with semaphore:
        for attempt in range(1, RETRY_ATTEMPTS + 1):
            try:
                async with session.get(
                    url,
                    headers={"Referer": f"{BASE_URL}/bidding/bid/getBidResultView/{result_id}"},
                    timeout=aiohttp.ClientTimeout(total=REQUEST_TIMEOUT),
                ) as resp:
                    if resp.status == 200:
                        html = await resp.text()
                        parsed = _parse_evaluation_html(html, result_id)
                        if parsed.vendors or parsed.error == "login_required":
                            return parsed
                    elif resp.status in (404, 401, 403):
                        break
            except Exception as exc:
                logger.debug("Eval fetch error for %s (attempt %d): %s", result_id, attempt, exc)
            if attempt < RETRY_ATTEMPTS:
                await asyncio.sleep(RETRY_DELAY)


    return EvaluationDetail(result_id=result_id, error="not_available")


async def fetch_all_evaluations(
    result_ids: list[str],
    cookies: dict,
) -> dict[str, EvaluationDetail]:
    """Fetch evaluation details for all result_ids concurrently."""
    semaphore = asyncio.Semaphore(NUM_DETAIL_WORKERS)
    logger.info("Fetching evaluation details for %d bids...", len(result_ids))

    async with aiohttp.ClientSession(cookies=cookies) as session:
        tasks = [_fetch_evaluation(session, rid, semaphore) for rid in result_ids]
        results = await asyncio.gather(*tasks, return_exceptions=True)

    evals: dict[str, EvaluationDetail] = {}
    for rid, result in zip(result_ids, results):
        if isinstance(result, Exception):
            evals[rid] = EvaluationDetail(result_id=rid, error=str(result))
        else:
            evals[rid] = result

    found = sum(1 for e in evals.values() if e.vendors)
    logger.info("Evaluation details found for %d/%d bids", found, len(result_ids))
    return evals
