-- Add department column to courses table
ALTER TABLE courses ADD COLUMN IF NOT EXISTS department TEXT DEFAULT 'General';
