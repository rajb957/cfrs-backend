import kagglehub

# Download latest version
path = kagglehub.dataset_download("yakshshah/blog-recommendation-data")

print("Path to dataset files:", path)