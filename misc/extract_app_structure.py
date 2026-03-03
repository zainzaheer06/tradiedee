#!/usr/bin/env python3
"""
Script to help extract structure from app.py for reorganization
Analyzes app.py and identifies models, decorators, utility functions, and routes
"""

import re

def analyze_app_py():
    """Analyze app.py structure"""
    with open('app.py', 'r', encoding='utf-8') as f:
        content = f.read()

    lines = content.split('\n')

    # Find all class definitions (models)
    models = []
    decorators = []
    utility_functions = []
    routes = []

    for i, line in enumerate(lines, 1):
        # Find models (class definitions)
        if line.startswith('class ') and '(db.Model)' in line:
            class_name = line.split('class ')[1].split('(')[0].strip()
            models.append((i, class_name))

        # Find decorator functions
        if 'def ' in line and ('_required' in line or 'login_' in line or 'admin_' in line):
            func_name = re.search(r'def\s+(\w+)', line)
            if func_name:
                decorators.append((i, func_name.group(1)))

        # Find routes
        if '@app.route(' in line:
            route_match = re.search(r"@app.route\('([^']+)'", line)
            if route_match:
                route_path = route_match.group(1)
                # Get function name from next few lines
                for j in range(i, min(i+3, len(lines))):
                    if 'def ' in lines[j]:
                        func_match = re.search(r'def\s+(\w+)', lines[j])
                        if func_match:
                            routes.append((i, route_path, func_match.group(1)))
                            break

    print("=" * 70)
    print("APP.PY STRUCTURE ANALYSIS")
    print("=" * 70)

    print(f"\n[MODELS] FOUND ({len(models)}):")
    for line_num, model_name in models:
        print(f"  Line {line_num}: {model_name}")

    print(f"\n[DECORATORS] FOUND ({len(decorators)}):")
    for line_num, dec_name in decorators:
        print(f"  Line {line_num}: {dec_name}")

    print(f"\n[ROUTES] FOUND ({len(routes)}):")

    # Group routes by category
    agent_routes = [r for r in routes if '/agent' in r[1]]
    campaign_routes = [r for r in routes if '/campaign' in r[1] or '/outbound' in r[1]]
    inbound_routes = [r for r in routes if '/inbound' in r[1] and '/campaign' not in r[1]]
    tool_routes = [r for r in routes if '/tool' in r[1]]
    admin_routes = [r for r in routes if '/admin' in r[1]]
    auth_routes = [r for r in routes if any(x in r[1] for x in ['/login', '/signup', '/logout', '/verify'])]
    main_routes = [r for r in routes if r[1] in ['/', '/dashboard', '/subscription', '/homepage', '/web-call', '/call-log', '/pending-approval']]
    api_routes = [r for r in routes if '/api' in r[1] or '/webhook' in r[1]]

    print(f"\n  [AGENTS] ({len(agent_routes)} routes):")
    for line_num, path, func in agent_routes[:10]:  # Show first 10
        print(f"    Line {line_num}: {path} -> {func}()")

    print(f"\n  [CAMPAIGNS] ({len(campaign_routes)} routes):")
    for line_num, path, func in campaign_routes[:10]:
        print(f"    Line {line_num}: {path} -> {func}()")

    print(f"\n  [INBOUND] ({len(inbound_routes)} routes):")
    for line_num, path, func in inbound_routes:
        print(f"    Line {line_num}: {path} -> {func}()")

    print(f"\n  [TOOLS] ({len(tool_routes)} routes):")
    for line_num, path, func in tool_routes:
        print(f"    Line {line_num}: {path} -> {func}()")

    print(f"\n  [ADMIN] ({len(admin_routes)} routes):")
    for line_num, path, func in admin_routes:
        print(f"    Line {line_num}: {path} -> {func}()")

    print(f"\n  [AUTH] ({len(auth_routes)} routes):")
    for line_num, path, func in auth_routes:
        print(f"    Line {line_num}: {path} -> {func}()")

    print(f"\n  [MAIN/CORE] ({len(main_routes)} routes):")
    for line_num, path, func in main_routes:
        print(f"    Line {line_num}: {path} -> {func}()")

    print(f"\n  [API/WEBHOOKS] ({len(api_routes)} routes):")
    for line_num, path, func in api_routes:
        print(f"    Line {line_num}: {path} -> {func}()")

    print("\n" + "=" * 70)
    print(f"TOTAL ROUTES: {len(routes)}")
    print("=" * 70)

    return {
        'models': models,
        'decorators': decorators,
        'routes': routes,
        'agent_routes': agent_routes,
        'campaign_routes': campaign_routes,
        'inbound_routes': inbound_routes,
        'tool_routes': tool_routes,
        'admin_routes': admin_routes,
        'auth_routes': auth_routes,
        'main_routes': main_routes,
        'api_routes': api_routes,
    }

if __name__ == '__main__':
    analyze_app_py()
