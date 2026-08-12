INSERT INTO users (user_id, username, friendly_name, thumb, custom_avatar_url) VALUES
  (1, 'fixture-admin', 'Fixture Admin', '/user/1', ''),
  (2, 'fixture-guest', 'Fixture Guest', '/user/2', '');

INSERT INTO library_sections (server_id, section_id, section_name, section_type, thumb, art, count, parent_count, child_count, deleted_section) VALUES
  ('server-fixture', 1, 'Fixture Movies', 'movie', '/library/1', '/art/1', 1, 0, 0, 0),
  ('server-fixture', 2, 'Fixture TV', 'show', '/library/2', '/art/2', 1, 1, 2, 0),
  ('server-fixture', 3, 'Fixture Music', 'artist', '/library/3', '/art/3', 1, 1, 1, 0);

INSERT INTO session_history (id, reference_id, started, stopped, rating_key, user_id, user, ip_address, paused_counter, player, product, product_version, platform, platform_version, profile, machine_id, bandwidth, location, quality_profile, secure, relayed, parent_rating_key, grandparent_rating_key, media_type, section_id, view_offset) VALUES
  (1, 1, 1704067200, 1704067800, 101, 1, 'fixture-admin', '192.0.2.10', 60, 'Fixture Browser', 'Plex Web', '1', 'Chrome', '1', '', 'device-1', 8000, 'lan', 'Original', 1, 0, 0, 0, 'movie', 1, 600000),
  (2, 2, 1704153600, 1704154100, 101, 2, 'fixture-guest', '192.0.2.11', 0, 'Fixture TV', 'Plex Android', '1', 'Android', '13', '', 'device-2', 4000, 'wan', '4 Mbps 720p', 1, 0, 0, 0, 'movie', 1, 500000),
  (3, 3, 1704240000, 1704240600, 202, 1, 'fixture-admin', '192.0.2.10', 0, 'Fixture Browser', 'Plex Web', '1', 'Chrome', '1', '', 'device-1', 8000, 'lan', 'Original', 1, 0, 201, 200, 'episode', 2, 1200000),
  (4, 4, 1704326400, 1704326580, 302, 1, 'fixture-admin', '192.0.2.10', 0, 'Fixture Browser', 'Plex Web', '1', 'Chrome', '1', '', 'device-1', 320, 'lan', 'Original', 1, 0, 301, 300, 'track', 3, 180000),
  (5, 5, 1704240100, 1704240700, 203, 2, 'fixture-guest', '192.0.2.11', 0, 'Fixture TV', 'Plex Android', '1', 'Android', '13', '', 'device-2', 4000, 'wan', 'Original', 1, 0, 201, 200, 'episode', 2, 1200000);

INSERT INTO session_history_metadata (id, rating_key, parent_rating_key, grandparent_rating_key, title, parent_title, grandparent_title, original_title, full_title, media_index, parent_media_index, thumb, parent_thumb, grandparent_thumb, art, media_type, year, originally_available_at, added_at, content_rating, rating, duration, guid, labels, live) VALUES
  (1, 101, 0, 0, 'Example Movie', '', '', 'Example Movie', 'Example Movie', 0, 0, '/movie', '', '', '/movie/art', 'movie', 2024, '2024-01-01', 1704060000, 'PG', '8.0', 600000, 'plex://movie/sanitized', 'fixture', 0),
  (2, 101, 0, 0, 'Example Movie', '', '', 'Example Movie', 'Example Movie', 0, 0, '/movie', '', '', '/movie/art', 'movie', 2024, '2024-01-01', 1704060000, 'PG', '8.0', 600000, 'plex://movie/sanitized', 'fixture', 0),
  (3, 202, 201, 200, 'Pilot', 'Season 1', 'Example Series', 'Pilot', 'Example Series - S01 E01 - Pilot', 1, 1, '/episode/1', '/season', '/series', '/series/art', 'episode', 2024, '2024-01-02', 1704150000, 'TV-PG', '8.5', 1200000, 'plex://episode/sanitized-1', '', 0),
  (4, 302, 301, 300, 'Example Track', 'Example Album', 'Example Artist', 'Example Track', 'Example Artist - Example Album - Example Track', 1, 1, '/track', '/album', '/artist', '/artist/art', 'track', 2024, '2024-01-03', 1704240000, '', '', 180000, 'plex://track/sanitized', '', 0),
  (5, 203, 201, 200, 'Second', 'Season 1', 'Example Series', 'Second', 'Example Series - S01 E02 - Second', 2, 1, '/episode/2', '/season', '/series', '/series/art', 'episode', 2024, '2024-01-02', 1704150000, 'TV-PG', '8.0', 1200000, 'plex://episode/sanitized-2', '', 0);

INSERT INTO session_history_media_info (id, rating_key, video_decision, audio_decision, transcode_decision, duration, container, bitrate, video_codec, video_resolution, audio_codec, audio_channels, stream_container, stream_container_decision, stream_bitrate, stream_video_decision, stream_video_codec, stream_video_resolution, stream_audio_decision, stream_audio_codec, stream_audio_channels) VALUES
  (1, 101, 'direct play', 'direct play', 'direct play', 600000, 'mkv', 8000, 'h264', '1080', 'aac', 2, 'mkv', 'direct play', 8000, 'direct play', 'h264', '1080', 'direct play', 'aac', 2),
  (2, 101, 'transcode', 'copy', 'transcode', 600000, 'mkv', 8000, 'h264', '1080', 'aac', 2, 'mkv', 'transcode', 4000, 'transcode', 'h264', '720', 'copy', 'aac', 2),
  (3, 202, 'direct play', 'direct play', 'direct play', 1200000, 'mkv', 8000, 'h264', '1080', 'aac', 2, 'mkv', 'direct play', 8000, 'direct play', 'h264', '1080', 'direct play', 'aac', 2),
  (4, 302, '', 'direct play', 'direct play', 180000, 'mp3', 320, '', '', 'mp3', 2, 'mp3', 'direct play', 320, '', '', '', 'direct play', 'mp3', 2),
  (5, 203, 'direct play', 'direct play', 'direct play', 1200000, 'mkv', 8000, 'h264', '1080', 'aac', 2, 'mkv', 'direct play', 8000, 'direct play', 'h264', '1080', 'direct play', 'aac', 2);
