import ipaddress
import timeit

def test_ip_range(start_val, end_val):
    start_ip = int(ipaddress.IPv4Address(start_val))
    end_ip = int(ipaddress.IPv4Address(end_val))
    return [str(ipaddress.IPv4Address(ip)) for ip in range(start_ip, end_ip + 1)]

def test_cidr_network(start_val, end_val, suffix):
    start_ip = ipaddress.IPv4Address(start_val)
    end_ip = ipaddress.IPv4Address(end_val)
    network = ipaddress.IPv4Network(f"{start_val}{suffix}", strict=False)
    results = []
    for ip in network:
        if ip < start_ip:
            continue
        if ip > end_ip:
            break
        results.append(str(ip))
    return results

if __name__ == "__main__":
    start = "10.0.0.5"
    end = "10.10.0.8"
    suffix = "/16" # Network 10.0.0.0/16
    
    # Logic check
    res1 = test_ip_range(start, end)
    res2 = test_cidr_network(start, end, suffix)
    print(f"Logic match: {res1 == res2}")
    
    # Performance check
    t1 = timeit.timeit(lambda: test_ip_range(start, end), number=10)
    t2 = timeit.timeit(lambda: test_cidr_network(start, end, suffix), number=10)
    
    print(f"IP Range time: {t1:.4f}s")
    print(f"CIDR Network time: {t2:.4f}s")
