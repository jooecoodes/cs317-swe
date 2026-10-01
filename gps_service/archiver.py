import sqlite3
import msgpack
import json
import zipfile
import datetime
import os
import argparse

DB_PATH = "./tracking.db"
EXPORT_DIR = "./exports"

def build_geojson(rows):
    features = []
    ids_to_delete = []
    
    for row_id, device_id, blob in rows:
        points = msgpack.unpackb(blob)
        ids_to_delete.append(row_id)
        
        # Leaflet and GeoJSON expect coordinates as [longitude, latitude]
        coordinates = [[p["lon"], p["lat"]] for p in points]
        
        features.append({
            "type": "Feature",
            "properties": {
                "device_id": device_id,
                "total_points": len(points)
            },
            "geometry": {
                "type": "LineString",
                "coordinates": coordinates
            }
        })
        
    return {"type": "FeatureCollection", "features": features}, ids_to_delete

def run_archive(target_date, device_id=None):
    os.makedirs(EXPORT_DIR, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Determine if we are archiving ALL devices or just ONE specific device
    if device_id:
        cursor.execute("SELECT id, device_id, path_blob FROM daily_tracking WHERE date = ? AND device_id = ?", (target_date, device_id))
        filename_base = f"track_{device_id}_{target_date}"
    else:
        cursor.execute("SELECT id, device_id, path_blob FROM daily_tracking WHERE date = ?", (target_date,))
        filename_base = f"track_ALL_{target_date}"
        
    rows = cursor.fetchall()
    
    if not rows:
        print(f"No data found for {target_date}" + (f" for device {device_id}." if device_id else "."))
        conn.close()
        return

    geojson_data, ids_to_delete = build_geojson(rows)

    json_path = f"{EXPORT_DIR}/{filename_base}.geojson"
    zip_path = f"{EXPORT_DIR}/{filename_base}.zip"

    # 1. Save to GeoJSON
    with open(json_path, "w") as f:
        json.dump(geojson_data, f)

    # 2. Compress to ZIP
    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
        zipf.write(json_path, os.path.basename(json_path))

    # 3. Clean up the uncompressed JSON file
    os.remove(json_path)

    # 4. Wipe the exported rows from the database
    placeholders = ','.join('?' for _ in ids_to_delete)
    cursor.execute(f"DELETE FROM daily_tracking WHERE id IN ({placeholders})", ids_to_delete)
    conn.commit()
    conn.close()

    print(f"Success: Archived {len(rows)} record(s) into {zip_path} and wiped them from the database.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Export and wipe GPS tracking data.")
    parser.add_argument("--date", help="Date to archive (YYYY-MM-DD). Defaults to yesterday.")
    parser.add_argument("--device", help="Specific device ID to archive. If omitted, archives all devices.")
    
    args = parser.parse_args()
    
    # If no date is passed, calculate yesterday's date
    archive_date = args.date if args.date else (datetime.date.today() - datetime.timedelta(days=1)).isoformat()
    
    run_archive(archive_date, args.device)
