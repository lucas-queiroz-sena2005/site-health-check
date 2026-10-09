from sqlmodel import Session, select
from api.database import engine
from api.models import HostState, ScanRun
import json

def fix_db():
    with Session(engine) as session:
        hosts = session.exec(select(HostState).where(HostState.metadata_resolved_from == None)).all()
        print(f"Found {len(hosts)} hosts with null resolved_from")
        
        runs = {}
        for host in hosts:
            if host.scan_run_id not in runs:
                run = session.get(ScanRun, host.scan_run_id)
                if run and run.snapshot_json:
                    runs[host.scan_run_id] = json.loads(run.snapshot_json).get("targets", [])
                else:
                    runs[host.scan_run_id] = []
                    
            targets = runs[host.scan_run_id]
            if targets:
                host.metadata_resolved_from = targets[0]
                session.add(host)
                
        session.commit()
        print("Fixed database!")

if __name__ == "__main__":
    fix_db()
