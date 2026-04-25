# Run this on your LOCAL machine where you're logged into YouTube
import browser_cookie3
import os

def export_youtube_cookies(output_file="cookies.txt"):
    """Export YouTube cookies to Netscape format"""
    try:
        # Try to get cookies from Chrome
        cj = browser_cookie3.chrome(domain_name='youtube.com')
        
        with open(output_file, 'w') as f:
            f.write("# Netscape HTTP Cookie File\n")
            count = 0
            for cookie in cj:
                if 'youtube.com' in cookie.domain:
                    # Format: domain\tflag\tpath\tsecure\texpires\tname\tvalue
                    domain = cookie.domain
                    flag = 'TRUE' if domain.startswith('.') else 'FALSE'
                    path = cookie.path
                    secure = 'TRUE' if cookie.secure else 'FALSE'
                    expires = int(cookie.expires) if cookie.expires else 0
                    name = cookie.name
                    value = cookie.value
                    
                    f.write(f"{domain}\t{flag}\t{path}\t{secure}\t{expires}\t{name}\t{value}\n")
                    count += 1
            
            print(f"✅ Exported {count} cookies to {output_file}")
            return True
            
    except Exception as e:
        print(f"❌ Error: {e}")
        return False

if __name__ == "__main__":
    export_youtube_cookies()
    
    # Show how to use in environment variable
    with open("cookies.txt", "r") as f:
        content = f.read()
        print("\n📋 To use in environment variable:")
        print("YOUTUBE_COOKIES=\"\"\"")
        print(content)
        print("\"\"\"")
