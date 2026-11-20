-- 研究对照模块：客群构成版本与对照结论（SQLAlchemy metadata 幂等建表，此文件为结构留档）。
-- audience_profiles：每次更新整体插入新版本，历史版本不可变；对照在受理时锁定同版分组、占比与组合限制。
CREATE TABLE IF NOT EXISTS audience_profiles (
  id INT AUTO_INCREMENT PRIMARY KEY,
  name VARCHAR(160) NOT NULL,
  payload JSON NOT NULL,
  created_by VARCHAR(120) NOT NULL,
  created_at VARCHAR(40) NOT NULL
);
CREATE TABLE IF NOT EXISTS comparisons (
  id INT AUTO_INCREMENT PRIMARY KEY,
  name VARCHAR(160) NOT NULL,
  run_a_id INT NOT NULL,
  run_b_id INT NOT NULL,
  profile_version INT NOT NULL,
  profile_snapshot JSON NOT NULL,
  result JSON NOT NULL,
  verdict VARCHAR(20) NOT NULL,
  created_by VARCHAR(120) NOT NULL,
  created_at VARCHAR(40) NOT NULL,
  CONSTRAINT fk_comparison_run_a FOREIGN KEY (run_a_id) REFERENCES recommendation_runs (id),
  CONSTRAINT fk_comparison_run_b FOREIGN KEY (run_b_id) REFERENCES recommendation_runs (id)
);
