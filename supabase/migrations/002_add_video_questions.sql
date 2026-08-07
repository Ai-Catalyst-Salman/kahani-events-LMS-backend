-- 002_add_video_questions.sql
-- Create table for storing quiz questions specific to a video

create table if not exists video_questions (
  id uuid primary key default gen_random_uuid(),
  video_id uuid not null references videos(id) on delete cascade,
  question text not null,
  options jsonb not null, -- Array of strings
  correct_option_index integer not null,
  created_at timestamptz default now()
);
