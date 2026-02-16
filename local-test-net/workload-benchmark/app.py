from flask import Flask, render_template, jsonify
from pathlib import Path
import re
from datetime import datetime

app = Flask(__name__)

# Configure log directory
LOG_DIR = Path('/experimental_logs')

def parse_log_file(filepath):
    """Parse log file to extract RPS and latency data"""
    data = {
        'experiment_name': '',
        'scheduler': '',
        'timestamp': '',
        'steps': [],
        'summary': {}
    }
    
    try:
        with open(filepath, 'r') as f:
            content = f.read()
            
        # Extract experiment info
        if match := re.search(r'SCHEDULED EXPERIMENT: (\w+)', content):
            data['scheduler'] = match.group(1)
        
        if match := re.search(r'Started: ([\d-]+ [\d:]+)', content):
            data['timestamp'] = match.group(1)
        
        # Extract step data from EXPERIMENT SUMMARY section
        summary_section = re.search(r'EXPERIMENT SUMMARY\n={80}\n(.*?)\n={80}', content, re.DOTALL)
        if summary_section:
            summary_lines = summary_section.group(1).strip().split('\n')
            for line in summary_lines:
                # Parse lines like: "Step 1:        1 RPS - SUCCESS - Avg latency: 0.259s"
                if match := re.match(r'Step\s+\d+:\s+(\d+)\s+RPS\s+-\s+(SUCCESS|OVERLOAD)\s+-\s+Avg latency:\s+([\d.]+)s', line):
                    rps = int(match.group(1))
                    status = match.group(2)
                    latency = float(match.group(3))
                    data['steps'].append({
                        'rps': rps,
                        'latency': latency,
                        'status': status
                    })
        
        data['experiment_name'] = filepath.stem
        
    except Exception as e:
        print(f"Error parsing {filepath}: {e}")
    
    return data

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/logs')
def list_logs():
    """List all log files with metadata"""
    if not LOG_DIR.exists():
        return jsonify([])
    
    logs = []
    for log_file in sorted(LOG_DIR.glob('experiment_*.log'), reverse=True):
        # Extract scheduler name and timestamp from filename
        # Format: experiment_fibonacci_20260215_181434.log
        match = re.match(r'experiment_(\w+)_([\d_]+)\.log', log_file.name)
        if match:
            scheduler = match.group(1)
            timestamp_str = match.group(2)
            # Parse timestamp
            dt = datetime.strptime(timestamp_str, '%Y%m%d_%H%M%S')
            
            logs.append({
                'filename': log_file.name,
                'scheduler': scheduler,
                'timestamp': dt.strftime('%Y-%m-%d %H:%M:%S'),
                'size': log_file.stat().st_size,
                'modified': log_file.stat().st_mtime
            })
    
    return jsonify(logs)

@app.route('/api/log/<filename>')
def get_log_content(filename):
    """Get content of a specific log file"""
    log_file = LOG_DIR / filename
    if not log_file.exists():
        return jsonify({'error': 'File not found'}), 404
    
    try:
        with open(log_file, 'r') as f:
            content = f.read()
        return jsonify({'content': content})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/log/<filename>/data')
def get_log_data(filename):
    """Get parsed data for graphing"""
    log_file = LOG_DIR / filename
    if not log_file.exists():
        return jsonify({'error': 'File not found'}), 404
    
    data = parse_log_file(log_file)
    return jsonify(data)

if __name__ == '__main__':
    # Run on all interfaces so it's accessible from outside Docker
    app.run(host='0.0.0.0', port=5000, debug=True)
