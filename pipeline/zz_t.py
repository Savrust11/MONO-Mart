target_date = "2026-06-17"
dt_to = target_date.replace("-","/")
dt_from = dt_to
print(f"FavoriteDTFrom = {dt_from}")
print(f"FavoriteDTTo   = {dt_to}")
print("単日(前日のみ)" if dt_from==dt_to else "範囲")
