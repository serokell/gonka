"""
Log Viewer Routes - Add these to your existing Flask application
"""
from flask import render_template, jsonify, request
from pathlib import Path
import re
from datetime import datetime

# Configure log directory
LOG_DIR = Path('/app/experimental_logs')

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
        
        # Extract step data from [LATENCY] Measurement complete sections
        # This regex captures the metrics block that appears after each step
        pattern = (
            r'\[LATENCY\] Measurement complete:\s*\n'
            r'\s*RPS:\s*([\d,]+)\s*\n'  # Match numbers with commas like "1,000"
            r'\s*Successful measurements:\s*\d+/\d+\s*\n'
            r'.*?'
            r'SERVER/API LATENCY:\s*\n'
            r'\s*Average:\s*([\d.]+)s'
            r'.*?'
            r'\s*Min:\s*([\d.]+)s'
            r'.*?'
            r'\s*Max:\s*([\d.]+)s'
            r'.*?'
            r'BLOCKCHAIN PROCESSING TIME \(until both confirmed\):\s*\n'
            r'\s*Average:\s*([\d.]+)s'
            r'.*?'
            r'\s*Min:\s*([\d.]+)s'
            r'.*?'
            r'\s*Max:\s*([\d.]+)s'
        )
        
        measurement_blocks = re.finditer(pattern, content, re.DOTALL)
        
        for match in measurement_blocks:
            rps_str = match.group(1).replace(',', '')  # Remove commas from RPS value
            rps = int(rps_str)
            
            # Server/API Latency
            server_avg = float(match.group(2))
            server_min = float(match.group(3))
            server_max = float(match.group(4))
            
            # Blockchain Processing Time
            blockchain_avg = float(match.group(5))
            blockchain_min = float(match.group(6))
            blockchain_max = float(match.group(7))
            
            data['steps'].append({
                'rps': rps,
                'server_latency_avg': server_avg,
                'server_latency_min': server_min,
                'server_latency_max': server_max,
                'blockchain_latency_avg': blockchain_avg,
                'blockchain_latency_min': blockchain_min,
                'blockchain_latency_max': blockchain_max
            })
        
        data['experiment_name'] = filepath.stem
        
    except Exception as e:
        print(f"Error parsing {filepath}: {e}")
    
    return data


def register_log_viewer_routes(app):
    """Register log viewer routes with your Flask app"""
    
    @app.route('/logs')
    def logs_viewer():
        """Main log viewer page"""
        return render_template('log_viewer.html')
    
    @app.route('/api/logs')
    def list_logs():
        """List all log files with metadata"""
        if not LOG_DIR.exists():
            return jsonify([])
        
        logs = []
        for log_file in LOG_DIR.glob('experiment_*.log'):
            # Extract scheduler name and timestamp from filename
            # Format: experiment_fibonacci_long_2_20260215_181434.log
            # Scheduler names can contain letters, numbers, and underscores
            match = re.match(r'experiment_([a-zA-Z0-9_]+)_(\d{8}_\d{6})\.log', log_file.name)
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
                    'modified': log_file.stat().st_mtime,
                    'sort_key': dt.timestamp()  # Unix timestamp for sorting
                })
        
        # Sort by timestamp, newest first
        logs.sort(key=lambda x: x['sort_key'], reverse=True)
        
        # Remove sort_key before returning
        for log in logs:
            del log['sort_key']
        
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
    
    @app.route('/api/run-experiment', methods=['POST'])
    def run_experiment():
        """Run an experiment with the provided parameters"""
        import subprocess
        
        try:
            data = request.get_json()
            
            # Validate required parameters
            if not data.get('schedule'):
                return jsonify({'error': 'Schedule is required'}), 400
            
            # Build command
            cmd = [
                'python', 'load_testing.py',
                '--schedule', str(data['schedule']),
                '--duration', str(data.get('duration', 15)),
                '--workers', str(data.get('workers', 300)),
                '--latency-delay', str(data.get('latencyDelay', 3)),
                '--latency-interval', str(data.get('latencyInterval', 2)),
                '--latency-count', str(data.get('latencyCount', 3))
            ]
            
            # Run in background (non-blocking)
            subprocess.Popen(
                cmd,
                cwd='/app',
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True
            )
            
            return jsonify({
                'status': 'started',
                'message': 'Experiment launched successfully',
                'parameters': data
            })
            
        except Exception as e:
            return jsonify({'error': str(e)}), 500
    
    @app.route('/api/schedules', methods=['GET'])
    def get_schedules():
        """Get all available schedules from schedules.json"""
        import json
        
        try:
            schedules_file = Path('/app/schedules.json')
            if not schedules_file.exists():
                return jsonify({})
            
            with open(schedules_file, 'r') as f:
                schedules = json.load(f)
            
            return jsonify(schedules)
            
        except Exception as e:
            return jsonify({'error': str(e)}), 500
    
    @app.route('/api/schedules', methods=['POST'])
    def add_schedule():
        """Add a new schedule to schedules.json"""
        import json
        
        try:
            data = request.get_json()
            name = data.get('name')
            values = data.get('values')
            
            # Validate
            if not name or not values:
                return jsonify({'error': 'Name and values are required'}), 400
            
            if not isinstance(values, list) or len(values) == 0:
                return jsonify({'error': 'Values must be a non-empty array'}), 400
            
            # Load existing schedules
            schedules_file = Path('/app/schedules.json')
            if schedules_file.exists():
                with open(schedules_file, 'r') as f:
                    schedules = json.load(f)
            else:
                schedules = {}
            
            # Check if already exists
            if name in schedules:
                return jsonify({'error': f'Schedule "{name}" already exists'}), 400
            
            # Add new schedule
            schedules[name] = values
            
            # Save back to file
            with open(schedules_file, 'w') as f:
                json.dump(schedules, f, indent=2)
            
            return jsonify({
                'status': 'success',
                'message': f'Schedule "{name}" added successfully',
                'schedule': {name: values}
            })
            
        except Exception as e:
            return jsonify({'error': str(e)}), 500
    
    print("✓ Log viewer routes registered at /logs")
