from app.services.sector_service import SectorService
import json

def test():
    print("Fetching Sector Rotation Data...")
    data = SectorService.get_rotation_data()
    print(f"Success! Found data for {len(data)} sectors.")
    
    # Print sample for a sector
    if data:
        sample_key = list(data.keys())[0]
        sample_sector_data = data[sample_key]
        print(f"\nSample Sector: {sample_key}")
        print(f"  Rank: {sample_sector_data.get('rank')}")
        print(f"  Commentary: {sample_sector_data.get('commentary')}")
        # Assuming 'current' and 'history' are still desired for the sample
        if 'current' in sample_sector_data:
            print(f"  Current RS: {sample_sector_data['current'].get('rs')}")
            print(f"  Current RM: {sample_sector_data['current'].get('rm')}")
        if 'history' in sample_sector_data:
            print(f"  History Count: {len(sample_sector_data['history'])}")
        
if __name__ == "__main__":
    test()
