import argparse
import json

from database import get_remote_database_location
from remote_utils import close_ssh_connection, get_ssh_connection, run_remote_sql


INTERVIEW_COLUMNS = [
    "interview_id",
    "student_id",
    "name",
    "company",
    "interview_type",
    "timestamp",
    "duration_minutes",
    "model",
    "model_reasoning_level",
]

PROGRESS_COLUMNS = [
    "student_id",
    "name",
    "interview_type",
    "completion_timestamp",
]


def build_parser():
    parser = argparse.ArgumentParser(
        description="Inspect interview data stored in the remote LIACS SQLite database."
    )
    parser.add_argument(
        "--table",
        choices=["interviews", "progress"],
        default="interviews",
        help="Which table to inspect.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=20,
        help="How many rows to return.",
    )
    parser.add_argument(
        "--student-id",
        default="",
        help="Optional student_id filter.",
    )
    parser.add_argument(
        "--interview-type",
        default="",
        help="Optional interview_type filter.",
    )
    parser.add_argument(
        "--session-id",
        dest="interview_id",
        default="",
        help="Optional interview/session id filter.",
    )
    parser.add_argument(
        "--show-summary",
        action="store_true",
        help="Include the summary column for interview rows.",
    )
    parser.add_argument(
        "--show-transcript",
        action="store_true",
        help="Include the transcript column for interview rows.",
    )
    parser.add_argument(
        "--count-only",
        action="store_true",
        help="Print only the number of matching rows.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print results as JSON instead of tab-separated text.",
    )
    return parser


def build_query(args):
    params = []
    where_clauses = []

    if args.interview_id:
        if args.table != "interviews":
            raise ValueError("--session-id can only be used with the interviews table.")
        where_clauses.append("interview_id = ?")
        params.append(args.interview_id)
    if args.student_id:
        where_clauses.append("student_id = ?")
        params.append(args.student_id)
    if args.interview_type:
        where_clauses.append("interview_type = ?")
        params.append(args.interview_type)

    where_sql = ""
    if where_clauses:
        where_sql = " WHERE " + " AND ".join(where_clauses)

    if args.count_only:
        query = f"SELECT COUNT(*) FROM {args.table}{where_sql}"
        return query, params, ["count"]

    if args.table == "interviews":
        columns = list(INTERVIEW_COLUMNS)
        if args.show_summary:
            columns.append("summary")
        if args.show_transcript:
            columns.append("transcript")
        order_column = "timestamp"
    else:
        columns = list(PROGRESS_COLUMNS)
        order_column = "completion_timestamp"

    query = (
        f"SELECT {', '.join(columns)} FROM {args.table}{where_sql} "
        f"ORDER BY {order_column} DESC LIMIT ?"
    )
    params.append(args.limit)
    return query, params, columns


def print_rows(columns, rows, as_json=False):
    if as_json:
        objects = [dict(zip(columns, row)) for row in rows]
        print(json.dumps(objects, indent=2))
        return

    print("\t".join(columns))
    for row in rows:
        print("\t".join("" if value is None else str(value) for value in row))


def main():
    args = build_parser().parse_args()
    _, db_path = get_remote_database_location()
    query, params, columns = build_query(args)

    ssh = None
    tmp_key_path = None
    try:
        ssh, tmp_key_path = get_ssh_connection()
        rows = run_remote_sql(ssh, db_path, query, params, fetch="all") or []
    finally:
        close_ssh_connection(ssh, tmp_key_path)

    if args.count_only:
        count = rows[0][0] if rows else 0
        if args.json:
            print(json.dumps({"count": count}))
        else:
            print(count)
        return

    print_rows(columns, rows, as_json=args.json)


if __name__ == "__main__":
    main()
