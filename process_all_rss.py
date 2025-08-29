#!/usr/bin/env python3
"""
RSS 컬렉션 전체 배치 처리 스크립트
- 모든 RSS 엔트리에 대해 키워드, 태그, 카테고리 추출
- 결과를 MongoDB에 저장
- 기존에 처리된 데이터는 자동으로 건너뛰기 (효율성 개선)

사용 예시:
  python process_all_rss.py --test                    # 테스트 모드 (5개 엔트리만)
  python process_all_rss.py --batch-size 100         # 배치 크기 100으로 실행
  python process_all_rss.py --no-tags                 # 태그 추출 비활성화
  python process_all_rss.py --no-categories           # 카테고리 추출 비활성화
  python process_all_rss.py --force-all               # 모든 엔트리 강제 재처리
  python process_all_rss.py --force-keywords          # 키워드만 강제 재처리
  python process_all_rss.py --tags-from-keywords      # 기존 키워드로 태그만 빠르게 추출
"""

import time
import sys
from typing import List, Dict, Any
from app.services.mongo_simple import mongo
from app.models import ExtractIn, TextIn, ExtractOptions, OptKeywords, OptTags, OptCategories
from app.api import extract

# Rich imports for beautiful console output
from rich.console import Console
from rich.progress import Progress, TaskID, SpinnerColumn, BarColumn, TextColumn, TimeElapsedColumn, TimeRemainingColumn
from rich.table import Table
from rich.panel import Panel
from rich import box
from rich.text import Text

# Initialize rich console
console = Console()


def process_rss_batch(skip: int = 0, limit: int = 50, save_results: bool = True, 
                      use_tags: bool = True, use_categories: bool = True, 
                      skip_existing_keywords: bool = True, skip_existing_tags: bool = True, skip_existing_categories: bool = True,
                      ollama_server: str = None, ollama_model: str = None, 
                      progress: Progress = None, task_id: TaskID = None) -> Dict[str, Any]:
    """RSS 엔트리 배치 처리"""
    if progress and task_id:
        progress.update(task_id, description="[cyan]엔트리 가져오는 중...")
    else:
        console.print(f"\n[bold cyan]=== 배치 처리 시작: skip={skip}, limit={limit} ===[/bold cyan]")
    
    # RSS 엔트리 가져오기 (필터링 조건 구성)
    
    # 필터 조건 구성
    filter_conditions = []
    
    # 키워드 기반 태그 추출 모드: 키워드는 있지만 태그가 없는 엔트리들 대상
    if use_tags and not use_categories and skip_existing_keywords:
        # 키워드는 있지만 태그가 없는 엔트리들만 대상
        filter_conditions.append({
            "keywords": {"$exists": True, "$ne": [], "$ne": None, "$not": {"$size": 0}}
        })
        if skip_existing_tags:
            filter_conditions.append({"$or": [
                {"tags": {"$exists": False}},
                {"tags": {"$size": 0}},
                {"tags": None}
            ]})
    else:
        # 기존 로직 유지
        if skip_existing_keywords:
            filter_conditions.append({"$or": [
                {"keywords": {"$exists": False}},
                {"keywords": {"$size": 0}},
                {"keywords": None}
            ]})
        
        if skip_existing_tags and use_tags:
            filter_conditions.append({"$or": [
                {"tags": {"$exists": False}},
                {"tags": {"$size": 0}},
                {"tags": None}
            ]})
        
        if skip_existing_categories and use_categories:
            filter_conditions.append({"$or": [
                {"categories": {"$exists": False}},
                {"categories": {"$size": 0}},
                {"categories": None}
            ]})
    
    # 필터 딕셔너리 구성
    filter_dict = {}
    if filter_conditions:
        filter_dict = {"$and": filter_conditions}
    
    entries = mongo.get_rss_entries(limit=limit, skip=skip, filter_dict=filter_dict)
    
    if not entries:
        if progress and task_id:
            progress.update(task_id, description="[yellow]처리할 엔트리 없음")
        else:
            console.print("[yellow]처리할 엔트리가 없습니다.[/yellow]")
        return {"processed": 0, "skipped": 0, "errors": 0}
    
    if progress and task_id:
        progress.update(task_id, description=f"[cyan]엔트리 {len(entries)}개 변환 중...")
    else:
        console.print(f"[green]가져온 엔트리 수: {len(entries)}[/green]")
    
    # TextIn 형식으로 변환 (기존 키워드 포함)
    texts = []
    for entry in entries:
        try:
            text_in = TextIn(
                id=entry.get('_id', 'unknown'),
                title=entry.get('title', ''),
                content=entry.get('description', ''),  # TextIn이 자동으로 content로 변환
                url=entry.get('url', ''),
                lang=entry.get('lang', 'en')
            )
            
            # 기존 키워드가 있으면 추가 (태그 추출에 활용)
            existing_keywords = entry.get('keywords', [])
            if existing_keywords:
                # TextIn 객체에 기존 키워드 정보 추가 (추후 extract에서 활용)
                text_in.existing_keywords = existing_keywords
            
            texts.append(text_in)
        except Exception as e:
            if not (progress and task_id):
                console.print(f"[red]TextIn 변환 오류 (ID: {entry.get('_id', 'unknown')}): {e}[/red]")
            continue
    
    if not texts:
        if progress and task_id:
            progress.update(task_id, description="[red]변환 가능한 엔트리 없음")
        else:
            console.print("[red]변환할 수 있는 엔트리가 없습니다.[/red]")
        return {"processed": 0, "skipped": len(entries), "errors": len(entries)}
    
    # Extract 처리
    if progress and task_id:
        progress.update(task_id, description=f"[yellow]키워드/태그/카테고리 추출 중... ({len(texts)}개)")
    else:
        console.print(f"[yellow]키워드/태그/카테고리 추출 중... ({len(texts)}개 엔트리)[/yellow]")
    
    try:
        # Ollama 모델 설정
        from app.core.config import settings
        server_name = ollama_server or settings.DEFAULT_OLLAMA_SERVER
        model_name = ollama_model or settings.DEFAULT_OLLAMA_MODEL
        
        extract_request = ExtractIn(
            texts=texts,
            options=ExtractOptions(
                keywords=OptKeywords(enable=True, algo='yake', top_k=10),
                tags=OptTags(enable=use_tags, model=model_name, top_k=8),
                categories=OptCategories(enable=use_categories, scheme='redfin-minds-2025', multi_label=True)
            )
        )
        
        result = extract(extract_request)
        
        if progress and task_id:
            progress.update(task_id, description=f"[green]처리 완료: {len(result.results)}개")
        else:
            console.print(f"[green]처리 완료: {len(result.results)}개 결과[/green]")
        
        # 결과 저장 (선택적)
        if save_results:
            if progress and task_id:
                progress.update(task_id, description="[cyan]MongoDB에 저장 중...")
            saved_count = save_results_to_mongo(result.results, entries)
            if progress and task_id:
                progress.update(task_id, description=f"[green]저장 완료: {saved_count}개")
            else:
                console.print(f"[green]MongoDB에 저장 완료: {saved_count}개[/green]")
        
        # 결과 요약 출력 (프로그레스바 사용 시에는 생략)
        if not (progress and task_id):
            print_processing_summary(result.results)
        
        return {
            "processed": len(result.results),
            "skipped": 0,
            "errors": 0,
            "total_keywords": sum(len(r.keywords) for r in result.results),
            "total_tags": sum(len(r.tags) for r in result.results),
            "total_categories": sum(len(r.categories) for r in result.results)
        }
        
    except Exception as e:
        if progress and task_id:
            progress.update(task_id, description=f"[red]오류 발생: {str(e)[:50]}...")
        else:
            console.print(f"[red]처리 중 오류 발생: {e}[/red]")
        return {"processed": 0, "skipped": len(texts), "errors": len(texts)}


def save_results_to_mongo(results: List[Any], original_entries: List[Dict[str, Any]]) -> int:
    """처리 결과를 MongoDB에 저장"""
    saved_count = 0
    
    for i, result in enumerate(results):
        try:
            if i < len(original_entries):
                entry_id = original_entries[i].get('_id')
                
                # 결과를 MongoDB 업데이트 형식으로 변환
                update_data = {
                    'processed': True,
                    'processed_at': int(time.time()),
                    'keywords': [kw.text for kw in result.keywords],
                    'keyword_scores': {kw.text: kw.score for kw in result.keywords},
                    'tags': result.tags,
                    'categories': [cat.name for cat in result.categories],
                    'category_scores': {cat.name: cat.score for cat in result.categories}
                }
                
                # MongoDB 업데이트
                mongo.update_document('rss_all_entries', entry_id, update_data)
                saved_count += 1
                
        except Exception as e:
            print(f"저장 오류 (인덱스 {i}): {e}")
    
    return saved_count


def print_processing_summary(results: List[Any]):
    """처리 결과 요약 출력 (Rich 사용)"""
    if not results:
        return
    
    total_keywords = sum(len(r.keywords) for r in results)
    total_tags = sum(len(r.tags) for r in results)
    total_categories = sum(len(r.categories) for r in results)
    
    # 요약 테이블 생성
    summary_table = Table(title="처리 결과 요약", box=box.ROUNDED)
    summary_table.add_column("항목", style="cyan", width=15)
    summary_table.add_column("개수", style="magenta", justify="right", width=10)
    
    summary_table.add_row("처리된 엔트리", str(len(results)))
    summary_table.add_row("추출된 키워드", str(total_keywords))
    summary_table.add_row("추출된 태그", str(total_tags))
    summary_table.add_row("추출된 카테고리", str(total_categories))
    
    console.print("\n")
    console.print(summary_table)
    
    # 첫 번째 결과 샘플 출력
    if results:
        sample = results[0]
        
        sample_panel = Panel.fit(
            f"[bold cyan]ID:[/bold cyan] {sample.id}\n\n"
            f"[bold yellow]키워드 ({len(sample.keywords)}개):[/bold yellow]\n"
            + "\n".join([f"  • {kw.text} ([green]{kw.score:.3f}[/green])" for kw in sample.keywords[:5]])
            + (f"\n  ... 그 외 {len(sample.keywords) - 5}개" if len(sample.keywords) > 5 else "")
            + f"\n\n[bold blue]태그 ({len(sample.tags)}개):[/bold blue]\n"
            + "\n".join([f"  • {tag}" for tag in sample.tags[:5]])
            + (f"\n  ... 그 외 {len(sample.tags) - 5}개" if len(sample.tags) > 5 else "")
            + f"\n\n[bold magenta]카테고리 ({len(sample.categories)}개):[/bold magenta]\n"
            + "\n".join([f"  • {cat.name} ([green]{cat.score:.3f}[/green])" for cat in sample.categories[:3]])
            + (f"\n  ... 그 외 {len(sample.categories) - 3}개" if len(sample.categories) > 3 else ""),
            title="[bold white]첫 번째 엔트리 결과 샘플[/bold white]",
            border_style="blue"
        )
        console.print(sample_panel)


def process_all_rss(batch_size: int = 50, max_batches: int = None, save_results: bool = True,
                    use_tags: bool = True, use_categories: bool = True,
                    skip_existing_keywords: bool = True, skip_existing_tags: bool = True, skip_existing_categories: bool = True,
                    ollama_server: str = None, ollama_model: str = None):
    """전체 RSS 컬렉션 처리"""
    
    # 시작 헤더 출력
    console.print(Panel.fit(
        "[bold cyan]RSS 컬렉션 전체 배치 처리[/bold cyan]",
        border_style="cyan"
    ))
    
    # 전체 문서 수 확인
    total_count = mongo.count_rss_entries()
    
    # 처리 완료 상태별 카운트
    keywords_done = mongo.count_rss_entries({"keywords": {"$exists": True, "$ne": [], "$ne": None}})
    tags_done = mongo.count_rss_entries({"tags": {"$exists": True, "$ne": [], "$ne": None}}) if use_tags else 0
    categories_done = mongo.count_rss_entries({"categories": {"$exists": True, "$ne": [], "$ne": None}}) if use_categories else 0
    
    # 상태 테이블 생성
    status_table = Table(title="처리 상태", box=box.ROUNDED)
    status_table.add_column("항목", style="cyan", width=20)
    status_table.add_column("완료", style="green", justify="right", width=10)
    status_table.add_column("전체", style="blue", justify="right", width=10)
    status_table.add_column("진행률", style="yellow", justify="right", width=10)
    
    status_table.add_row("전체 엔트리", "-", str(total_count), "-")
    status_table.add_row("키워드 추출", str(keywords_done), str(total_count), f"{keywords_done/total_count*100:.1f}%")
    if use_tags:
        status_table.add_row("태그 추출", str(tags_done), str(total_count), f"{tags_done/total_count*100:.1f}%")
    if use_categories:
        status_table.add_row("카테고리 추출", str(categories_done), str(total_count), f"{categories_done/total_count*100:.1f}%")
    
    console.print(status_table)
    
    # 필터 조건 구성하여 실제 처리할 엔트리 수 확인
    filter_conditions = []
    if skip_existing_keywords:
        filter_conditions.append({"$or": [
            {"keywords": {"$exists": False}},
            {"keywords": {"$size": 0}},
            {"keywords": None}
        ]})
    if skip_existing_tags and use_tags:
        filter_conditions.append({"$or": [
            {"tags": {"$exists": False}},
            {"tags": {"$size": 0}},
            {"tags": None}
        ]})
    if skip_existing_categories and use_categories:
        filter_conditions.append({"$or": [
            {"categories": {"$exists": False}},
            {"categories": {"$size": 0}},
            {"categories": None}
        ]})
    
    filter_dict = {}
    if filter_conditions:
        filter_dict = {"$and": filter_conditions}
    
    remaining_count = mongo.count_rss_entries(filter_dict)
    console.print(f"\n[bold yellow]처리 대상 엔트리: {remaining_count}[/bold yellow]")
    
    if remaining_count == 0:
        console.print("[green]처리할 엔트리가 없습니다![/green]")
        return
    
    # 배치 처리 실행 (프로그레스바 사용)
    total_processed = 0
    total_errors = 0
    batch_count = 0
    
    skip = 0  # 필터링으로 처리되므로 skip은 0부터 시작
    estimated_batches = (total_count + batch_size - 1) // batch_size
    if max_batches:
        estimated_batches = min(estimated_batches, max_batches)
    
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
        TimeElapsedColumn(),
        TimeRemainingColumn(),
        console=console
    ) as progress:
        main_task = progress.add_task("[cyan]전체 처리 진행률", total=estimated_batches)
        
        while skip < total_count:
            if max_batches and batch_count >= max_batches:
                console.print(f"\n[yellow]최대 배치 수 ({max_batches}) 도달. 처리 중단.[/yellow]")
                break
            
            batch_count += 1
            
            # 배치 태스크 추가
            batch_task = progress.add_task(f"[green]배치 {batch_count}", total=1)
            
            # 배치 처리
            batch_result = process_rss_batch(
                skip=skip, 
                limit=batch_size, 
                save_results=save_results,
                use_tags=use_tags,
                use_categories=use_categories,
                skip_existing_keywords=skip_existing_keywords,
                skip_existing_tags=skip_existing_tags,
                skip_existing_categories=skip_existing_categories,
                ollama_server=ollama_server,
                ollama_model=ollama_model,
                progress=progress,
                task_id=batch_task
            )
            
            total_processed += batch_result['processed']
            total_errors += batch_result['errors']
            
            # 배치 완료 표시
            progress.update(batch_task, completed=1)
            progress.update(main_task, advance=1)
            
            # 다음 배치로
            skip += batch_size
            
            # 잠시 대기 (시스템 부하 방지)
            time.sleep(0.5)
    
    # 최종 결과 출력
    final_table = Table(title="전체 처리 완료", box=box.DOUBLE_EDGE)
    final_table.add_column("항목", style="cyan", width=20)
    final_table.add_column("개수", style="green", justify="right", width=10)
    
    final_table.add_row("처리된 엔트리", str(total_processed))
    final_table.add_row("오류 발생", str(total_errors))
    final_table.add_row("완료된 배치", str(batch_count))
    
    console.print("\n")
    console.print(final_table)


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="RSS 컬렉션 배치 처리")
    parser.add_argument("--batch-size", type=int, default=50, help="배치 크기 (기본값: 50)")
    parser.add_argument("--max-batches", type=int, help="최대 배치 수 (테스트용)")
    parser.add_argument("--no-save", action="store_true", help="결과를 MongoDB에 저장하지 않음")
    parser.add_argument("--test", action="store_true", help="테스트 모드 (1개 배치만 처리)")
    parser.add_argument("--no-tags", action="store_true", help="태그 추출 비활성화 (기본적으로 활성화됨)")
    parser.add_argument("--no-categories", action="store_true", help="카테고리 추출 비활성화 (기본적으로 활성화됨)")
    parser.add_argument("--use-tags", action="store_true", help="태그 추출 활성화 (기본값, 하위 호환성)")  # 하위 호환성
    
    # 기존 처리된 항목 건너뛰기 옵션
    parser.add_argument("--force-keywords", action="store_true", help="이미 키워드가 있는 엔트리도 다시 처리")
    parser.add_argument("--force-tags", action="store_true", help="이미 태그가 있는 엔트리도 다시 처리")
    parser.add_argument("--force-categories", action="store_true", help="이미 카테고리가 있는 엔트리도 다시 처리")
    parser.add_argument("--force-all", action="store_true", help="모든 엔트리를 강제로 다시 처리")
    
    # 키워드 기반 태그 추출 옵션
    parser.add_argument("--tags-from-keywords", action="store_true", help="기존 키워드를 활용하여 태그만 추출 (빠른 처리)")
    
    parser.add_argument("--ollama-server", type=str, help="Ollama 서버 선택 (local/remote)")
    parser.add_argument("--ollama-model", type=str, help="Ollama 모델 선택")
    
    args = parser.parse_args()
    
    # 옵션 설정
    use_tags_final = not args.no_tags
    use_categories_final = not args.no_categories
    
    # 키워드 기반 태그 추출 모드
    if args.tags_from_keywords:
        use_tags_final = True
        use_categories_final = False  # 태그만 처리
        console.print("[bold yellow]키워드 기반 태그 추출 모드 활성화[/bold yellow]")
    
    # 기존 데이터 건너뛰기 설정
    skip_existing_keywords = not (args.force_keywords or args.force_all)
    skip_existing_tags = not (args.force_tags or args.force_all)
    skip_existing_categories = not (args.force_categories or args.force_all)
    
    if args.test:
        print("=== 테스트 모드 ===")
        result = process_rss_batch(
            skip=0, 
            limit=5, 
            save_results=not args.no_save,
            use_tags=use_tags_final,
            use_categories=use_categories_final,
            skip_existing_keywords=skip_existing_keywords,
            skip_existing_tags=skip_existing_tags,
            skip_existing_categories=skip_existing_categories,
            ollama_server=args.ollama_server,
            ollama_model=args.ollama_model
        )
        print(f"테스트 결과: {result}")
    else:
        process_all_rss(
            batch_size=args.batch_size,
            max_batches=args.max_batches,
            save_results=not args.no_save,
            use_tags=use_tags_final,
            use_categories=use_categories_final,
            skip_existing_keywords=skip_existing_keywords,
            skip_existing_tags=skip_existing_tags,
            skip_existing_categories=skip_existing_categories,
            ollama_server=args.ollama_server,
            ollama_model=args.ollama_model
        )
