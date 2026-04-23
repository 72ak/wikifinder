import requests
import re
import time
from collections import deque
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

class WikiNavigator:
    def __init__(self):
        self.S = requests.Session()
        retry = Retry(total=3, backoff_factor=0.5)
        adapter = HTTPAdapter(pool_connections=20, pool_maxsize=20, max_retries=retry)
        self.S.mount('https://', adapter)
        self.S.mount('http://', adapter)
        self.API_URL = "https://en.wikipedia.org/w/api.php"
        self.headers = {"User-Agent": "WikiNavigatorBot/1.0 (contact@example.com)"}

    def resolve_page(self, title):
        params = {
            "action": "query", "format": "json", "titles": title,
            "redirects": 1, "inprop": "url", "prop": "info"
        }
        try:
            data = self.S.get(self.API_URL, params=params, headers=self.headers, timeout=5).json()
            pages = data.get("query", {}).get("pages", {})
            for page_id, page_info in pages.items():
                if page_id == "-1":
                    return None, None
                return page_info.get("title"), page_info.get("fullurl")
        except Exception:
            return None, None

    def _api_query(self, params):
        params["redirects"] = 1 
        results = set()
        while True:
            try:
                response = self.S.get(self.API_URL, params=params, headers=self.headers, timeout=10)
                
                if response.status_code != 200:
                    print(f"\n{response.status_code}")
                    break
                
                data = response.json()
                
                if "query" in data and "pages" in data["query"]:
                    for _, page_data in data["query"]["pages"].items():
                        if "links" in page_data:
                            for link in page_data["links"]:
                                results.add(link["title"])
                        if "categories" in page_data:
                            for cat in page_data["categories"]:
                                results.add(cat["title"].replace("Category:", ""))
                                
                if "query" in data and "backlinks" in data["query"]:
                    for bl in data["query"]["backlinks"]:
                        results.add(bl["title"])

                if "continue" in data:
                    params.update(data["continue"])
                else:
                    break
            except Exception as e:
                print(f"\n{e}")
                break
        return results

    def get_forward_links(self, title):
        params = {
            "action": "query",
            "format": "json",
            "titles": title,
            "prop": "links|categories",
            "pllimit": "max",
            "cllimit": "max",
            "plnamespace": 0
        }
        return self._api_query(params)

    def get_backlinks(self, title):
        params = {
            "action": "query",
            "format": "json",
            "list": "backlinks",
            "bltitle": title,
            "bllimit": "max",
            "blnamespace": 0
        }
        return self._api_query(params)

    def get_context_snippet(self, source, target):
        params = {
            "action": "query",
            "format": "json",
            "titles": source,
            "prop": "extracts",
            "explaintext": True,
            "exlimit": 1
        }
        try:
            data = self.S.get(self.API_URL, params=params, headers=self.headers).json()
            pages = data["query"]["pages"]
            page_content = next(iter(pages.values())).get("extract", "")

            escaped_target = re.escape(target.split(' (')[0]) 
            
            pattern = re.compile(r"([^.\n]*?\b" + escaped_target + r"\b[^.\n]*\.)", re.IGNORECASE)
            
            match = pattern.search(page_content)
            if match:
                return match.group(1).strip()
            else:
                return f"(link found in metadata/categories, but '{target}' is likely hidden)"
        except:
            return "error retrieving text."

    def find_fewest_hops(self, start, end):
        print(f"searching for fewing links: {start} -> {end}")
        queue = deque([[start]])
        visited = {start}

        while queue:
            path = queue.popleft()
            node = path[-1]

            if node == end:
                return path

            if len(path) <= 2: 
                print(f"scanning: {node}...")

            links = self.get_forward_links(node)
            
            if end in links:
                return path + [end]

            for link in links:
                if link not in visited:
                    visited.add(link)
                    new_path = list(path)
                    new_path.append(link)
                    queue.append(new_path)
        return None

    def find_fastest_route(self, start, end):
        print(f"searching for quickest (bidirectional): {start} <-> {end}")
        
        src_queue = deque([start])
        dst_queue = deque([end])

        src_visited = {start: None} 
        dst_visited = {end: None}

        while src_queue and dst_queue:
            if len(src_queue) <= len(dst_queue):
                current = src_queue.popleft()
                links = self.get_forward_links(current)
                
                for link in links:
                    if link not in src_visited:
                        src_visited[link] = current
                        src_queue.append(link)
                        if link in dst_visited:
                            return self._construct_bidirectional_path(link, src_visited, dst_visited)
            else:
                current = dst_queue.popleft()
                links = self.get_backlinks(current)
                
                for link in links:
                    if link not in dst_visited:
                        dst_visited[link] = current
                        dst_queue.append(link)
                        if link in src_visited:
                            return self._construct_bidirectional_path(link, src_visited, dst_visited)
        return None

    def _construct_bidirectional_path(self, meeting_point, src_parents, dst_parents):
        path_start = []
        curr = meeting_point
        while curr:
            path_start.append(curr)
            curr = src_parents[curr]
        path_start.reverse()

        path_end = []
        curr = dst_parents[meeting_point] 
        while curr:
            path_end.append(curr)
            curr = dst_parents[curr]
        
        return path_start + path_end

    def print_result(self, path, s_url, e_url):
        print(f"\nresolved start: {s_url}")
        print(f"resolved end:   {e_url}")

        if not path:
            print("\nno path found. You win.")
            return

        print("\n" + "="*22)
        print(f"path found ({len(path)-1} links)")
        print("="*22)
        
        for i in range(len(path) - 1):
            source = path[i]
            target = path[i+1]
            url = f"https://en.wikipedia.org/wiki/{source.replace(' ', '_')}"
            
            print(f"\n[step {i+1}] {source} -> {target}")
            print(f"url: {url}")
            
            snippet = self.get_context_snippet(source, target)
            print(f"context: \"{snippet}\"")
            print("-" * 22)

if __name__ == "__main__":
    nav = WikiNavigator()
    
    s_raw = input("start page: ").strip()
    e_raw = input("end page:   ").strip()
    
    print("\nresolving pages...")
    s_title, s_url = nav.resolve_page(s_raw)
    e_title, e_url = nav.resolve_page(e_raw)

    if not s_title or not e_title:
        print("\nError: Could not resolve one or both pages on Wikipedia.")
        exit()
    
    print("\nselect algorithm:")
    print("1. shortest path/fewest links (bfs)")
    print("2. shortest time (bidirectional)")
    
    choice = input("choice (1/2): ")
    
    start_time = time.time()
    if choice == "1":
        path = nav.find_fewest_hops(s_title, e_title)
    else:
        path = nav.find_fastest_route(s_title, e_title)
    
    print(f"\nsearch time: {time.time() - start_time:.2f} seconds")
    nav.print_result(path, s_url, e_url)
