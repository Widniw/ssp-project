import os
import re
import glob
import matplotlib.pyplot as plt

def natural_sort_key(s):
    return [int(text) if text.isdigit() else text.lower()
            for text in re.split('([0-9]+)', s)]

def parse_iperf_intervals(filepath):

    # Regex matches lines like:
    # [  3]  0.0- 1.0 sec  1.12 MBytes  9.44 Mbits/sec
    # Group 1: Interval End Time (e.g., "1.0")
    # Group 2: Bandwidth Value (e.g., "9.44")
    # Group 3: Unit (e.g., "Mbits/sec")
    regex = r"-\s*(\d+(?:\.\d+)?)\s+sec.*?(\d+(?:\.\d+)?)\s+([KMG]bits\/sec)"
    
    data_points = []
    
    try:
        with open(filepath, 'r') as f:
            for line in f:
                match = re.search(regex, line)
                if match:
                    # We use the end of the interval as the timestamp
                    local_time = float(match.group(1))
                    val = float(match.group(2))
                    unit = match.group(3)
                    
                    # Normalize to Mbit/s
                    if unit == "Gbits/sec":
                        val *= 1000
                    elif unit == "Kbits/sec":
                        val /= 1000
                    
                    data_points.append((local_time, val))
    except Exception as e:
        print(f"Error reading {filepath}: {e}")
        return []

    return data_points

def main():
    target_folder = 'our_algorithm'
    start_delay_seconds = 2  # The stagger delay per file
    
    if not os.path.exists(target_folder):
        print(f"Error: Folder '{target_folder}' not found.")
        return

    # Get files and sort them naturally
    files = glob.glob(os.path.join(target_folder, '*'))
    files = [f for f in files if os.path.isfile(f)]
    files.sort(key=lambda x: natural_sort_key(os.path.basename(x)))

    if not files:
        print("No files found in directory.")
        return

    print(f"Found {len(files)} files. Plotting timeline...")

    plt.figure(figsize=(14, 7))
    
    # Iterate through sorted files
    for i, filepath in enumerate(files):
        filename = os.path.basename(filepath)
        label_name = os.path.splitext(filename)[0]
        
        # Calculate the global start time for this specific file
        # File 0 starts at 0s, File 1 at 2s, File 2 at 4s...
        global_offset = i * start_delay_seconds
        
        # Extract local data points
        local_data = parse_iperf_intervals(filepath)
        
        if not local_data:
            print(f"Warning: No valid data found in {filename}")
            continue
            
        # Adjust time by adding the global offset
        x_values = [t + global_offset for t, bw in local_data]
        y_values = [bw for t, bw in local_data]
        
        # Plot this pair's line
        plt.plot(x_values, y_values, label=label_name, linewidth=2)

    # Graph formatting
    plt.xlabel('Time (seconds)', fontsize=12)
    plt.ylabel('Throughput (Mbit/s)', fontsize=12)
    plt.title('Throughput Over Time (OSPF Algorithm)', fontsize=14)
    plt.grid(True, which='both', linestyle='--', alpha=0.7)
    
    # Legend - Place it outside if there are too many pairs
    plt.legend(bbox_to_anchor=(1.05, 1), loc='upper left', borderaxespad=0.)
    
    plt.tight_layout()
    
    output_image = 'throughput_timeline.png'
    plt.savefig(output_image)
    print(f"Graph saved as '{output_image}'")
    plt.show()

if __name__ == "__main__":
    main()