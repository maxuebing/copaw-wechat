import sys
import os
import importlib.util
import json

print("========== CoPaw Plugin Debug Tool ==========")
print(f"Python Executable: {sys.executable}")
print(f"Python Version: {sys.version.split()[0]}")

print("\n[Step 1] Checking Dependencies...")
missing_deps = []
try:
    import wechatpy
    print("✅ wechatpy: Installed")
except ImportError:
    print("❌ wechatpy: MISSING")
    missing_deps.append("wechatpy")

try:
    import cryptography
    print("✅ cryptography: Installed")
except ImportError:
    print("❌ cryptography: MISSING (Required by wechatpy)")
    missing_deps.append("cryptography")

try:
    import copaw
    print("✅ copaw: Installed")
except ImportError:
    print("❌ copaw: MISSING (Are you in the right venv?)")

if missing_deps:
    print(f"\n⚠️  CRITICAL: Missing dependencies! Please run:")
    print(f"   {sys.executable} -m pip install {' '.join(missing_deps)}")
    sys.exit(1)

print("\n[Step 2] Checking Plugin Directory...")
plugin_path = os.path.expanduser("~/.copaw/plugins/wechat")
if os.path.exists(plugin_path):
    print(f"✅ Plugin directory found: {plugin_path}")
    
    # Add plugins directory to sys.path to simulate CoPaw loading
    plugins_dir = os.path.dirname(plugin_path)
    if plugins_dir not in sys.path:
        sys.path.insert(0, plugins_dir)
    
    try:
        # Try importing the plugin package
        import wechat
        print("✅ Plugin package 'wechat' imported successfully")
        
        if hasattr(wechat, "create_plugin"):
             print("✅ 'create_plugin' function found")
        else:
             print("❌ 'create_plugin' function NOT found in __init__.py")
             
        # Verify Class Inheritance
        try:
            from copaw.app.channels.base import BaseChannel
            from wechat.plugin import WechatPlugin
            
            if issubclass(WechatPlugin, BaseChannel):
                print("✅ WechatPlugin correctly inherits from BaseChannel")
            else:
                print("❌ WechatPlugin does NOT inherit from BaseChannel")
                print(f"   Bases: {WechatPlugin.__bases__}")
        except Exception as e:
            print(f"⚠️  Inheritance check skipped: {e}")
            
    except ImportError as e:
        print(f"❌ Failed to import plugin: {e}")
        import traceback
        traceback.print_exc()
else:
    print(f"❌ Plugin directory NOT found: {plugin_path}")
    print("   Please ensure softlink is created:")
    print("   mkdir -p ~/.copaw/plugins")
    print("   ln -s $(pwd)/src/copaw_plugin_wechat ~/.copaw/plugins/wechat")

print("\n[Step 3] Checking Configuration...")
config_path = os.path.expanduser("~/.copaw/config.json")
if os.path.exists(config_path):
    print(f"✅ config.json found: {config_path}")
    try:
        with open(config_path, 'r') as f:
            config = json.load(f)
            
        if "wechat" in config:
            wechat_conf = config["wechat"]
            if wechat_conf.get("enabled", False):
                 print("✅ 'wechat' is ENABLED in config")
            else:
                 print("❌ 'wechat' is DISABLED in config (set 'enabled': true)")
        else:
            print("❌ 'wechat' key missing in config.json")
    except Exception as e:
        print(f"❌ Config check failed: {e}")
else:
    print(f"❌ config.json NOT found at {config_path}")

print("\n========== End of Debug ==========")
