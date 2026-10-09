import argparse
import asyncio

from app.domains.communications.outbox import process_email_batch


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Deliver queued TRANSPIRE transactional email")
    parser.add_argument("--watch", action="store_true", help="Continue polling for new messages")
    parser.add_argument("--batch-size", type=int, default=25)
    parser.add_argument("--poll-seconds", type=float, default=2.0)
    return parser.parse_args()


async def run() -> None:
    args = parse_args()
    while True:
        processed = await process_email_batch(limit=max(1, args.batch_size))
        if not args.watch:
            print(f"Processed {processed} queued email(s).")
            return
        if processed == 0:
            await asyncio.sleep(max(0.25, args.poll_seconds))


if __name__ == "__main__":
    asyncio.run(run())
