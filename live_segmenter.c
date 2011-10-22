/*
 * Copyright (c) 2009 Carson McDonald
 *
 * This program is free software; you can redistribute it and/or
 * modify it under the terms of the GNU General Public License version 2
 * as published by the Free Software Foundation.
 *
 * This program is distributed in the hope that it will be useful,
 * but WITHOUT ANY WARRANTY; without even the implied warranty of
 * MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
 * GNU General Public License for more details.
 *
 * You should have received a copy of the GNU General Public License
 * along with this program; if not, write to the Free Software
 * Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA  02110-1301, USA.
 *
 * Originaly created by and Copyright (c) 2009 Chase Douglas
 */

#include <stdio.h>
#include <string.h>
#include <unistd.h>
#include <time.h>

#include "libavformat/avformat.h"

#define PKT_WRITE_FRAME_ERROR_LIMIT 50

struct config_info
{
  const char *input_filename;
  int segment_length;
  const char *temp_directory;
  const char *filename_prefix;
  const char *encoding_profile;
  unsigned int start_from_segment;
  unsigned int run_cycle;
};

static AVStream *add_output_stream(AVFormatContext *output_format_context, AVStream *input_stream) 
{
  AVCodecContext *input_codec_context;
  AVCodecContext *output_codec_context;
  AVStream *output_stream;

  output_stream = av_new_stream(output_format_context, 0);
  if (!output_stream) 
  {
    fprintf(stderr, "Segmenter error: Could not allocate stream\n");
    exit(1);
  }

  input_codec_context = input_stream->codec;
  output_codec_context = output_stream->codec;

  output_codec_context->codec_id = input_codec_context->codec_id;
  output_codec_context->codec_type = input_codec_context->codec_type;
  output_codec_context->codec_tag = input_codec_context->codec_tag;
  output_codec_context->bit_rate = input_codec_context->bit_rate;
  output_codec_context->extradata = input_codec_context->extradata;
  output_codec_context->extradata_size = input_codec_context->extradata_size;

  if(av_q2d(input_codec_context->time_base) * input_codec_context->ticks_per_frame > av_q2d(input_stream->time_base) && av_q2d(input_stream->time_base) < 1.0/1000) 
  {
    output_codec_context->time_base = input_codec_context->time_base;
    output_codec_context->time_base.num *= input_codec_context->ticks_per_frame;
  }
  else 
  {
    output_codec_context->time_base = input_stream->time_base;
  }

  switch (input_codec_context->codec_type) 
  {
    case CODEC_TYPE_AUDIO:
      output_codec_context->channel_layout = input_codec_context->channel_layout;
      output_codec_context->sample_rate = input_codec_context->sample_rate;
      output_codec_context->channels = input_codec_context->channels;
      output_codec_context->frame_size = input_codec_context->frame_size;
      if ((input_codec_context->block_align == 1 && input_codec_context->codec_id == CODEC_ID_MP3) || input_codec_context->codec_id == CODEC_ID_AC3) 
      {
        output_codec_context->block_align = 0;
      }
      else 
      {
        output_codec_context->block_align = input_codec_context->block_align;
      }
      break;
    case CODEC_TYPE_VIDEO:
      output_codec_context->pix_fmt = input_codec_context->pix_fmt;
      output_codec_context->width = input_codec_context->width;
      output_codec_context->height = input_codec_context->height;
      output_codec_context->has_b_frames = input_codec_context->has_b_frames;

      if (output_format_context->oformat->flags & AVFMT_GLOBALHEADER) 
      {
          output_codec_context->flags |= CODEC_FLAG_GLOBAL_HEADER;
      }
      break;
    default:
      break;
  }

  return output_stream;
}

void output_transfer_command(const unsigned int sequence_number, const double segment_timestamp, const double duration_ms, const int end, const char *file_name)
{
  char buffer[1024 * 10];
  memset(buffer, 0, sizeof(char) * 1024 * 10);

  sprintf(buffer, "tstamp=%lf, sequence=%d, duration=%lf, end=%d, file=%s", segment_timestamp, sequence_number, duration_ms, end, file_name);

  fprintf(stderr, "segmenter: %s\n\r", buffer);
}


int segment_process(struct config_info config)

{
  unsigned int output_filename_size = sizeof(char) * (strlen(config.temp_directory) + 1 + strlen(config.filename_prefix) + 100);
  char *output_filename = malloc(output_filename_size);
 
  if (!output_filename) 
  {
    fprintf(stderr, "Segmenter error: Could not allocate space for output filenames\n");
    exit(1);
  }

  // ------------------ Done parsing input --------------

  // we try to approximate the time of first received frame
  // by taking system timestamp and storing first frame timestamp
  time_t sys_time; time(&sys_time);
  double  on_start_timestamp = (double)sys_time;

  av_register_all();

  AVInputFormat *input_format = av_find_input_format("mpegts");
  if (!input_format) 
  {
    fprintf(stderr, "Segmenter error: Could not find MPEG-TS demuxer\n");
    exit(1);
  }

  AVFormatContext *input_context = NULL;
  int ret = av_open_input_file(&input_context, config.input_filename, input_format, 0, NULL);
  if (ret != 0) 
  {
    fprintf(stderr, "Segmenter error: Could not open input file, make sure it is an mpegts file: %d\n", ret);
    exit(1);
  }

  if (av_find_stream_info(input_context) < 0) 
  {
    fprintf(stderr, "Segmenter error: Could not read stream information\n");
    exit(1);
  }

  //dump_format(input_context, 0, config.filename_prefix, 1);
  fprintf(stderr, "segmenter-debug: start time %lld %lld \n", input_context->start_time, input_context->timestamp);

#if LIBAVFORMAT_VERSION_MAJOR >= 52 && LIBAVFORMAT_VERSION_MINOR >= 45
  AVOutputFormat *output_format = av_guess_format("mpegts", NULL, NULL);
#else
  AVOutputFormat *output_format = guess_format("mpegts", NULL, NULL);
#endif
  if (!output_format) 
  {
    fprintf(stderr, "Segmenter error: Could not find MPEG-TS muxer\n");
    exit(1);
  }

  AVFormatContext *output_context = avformat_alloc_context();
  if (!output_context) 
  {
    fprintf(stderr, "Segmenter error: Could not allocated output context");
    exit(1);
  }
  output_context->oformat = output_format;

  int video_index = -1;
  int audio_index = -1;

  AVStream *video_stream;
  AVStream *audio_stream;

  int i;
  int index_map[20];
  memset (index_map, -1, sizeof(int)*20);

  for (i = 0; i < input_context->nb_streams && (video_index < 0 || audio_index < 0); i++) 
  {
    switch (input_context->streams[i]->codec->codec_type) {
      case CODEC_TYPE_VIDEO:
        video_index = i;
        input_context->streams[i]->discard = AVDISCARD_NONE;
        video_stream = add_output_stream(output_context, input_context->streams[i]);
	index_map[i] = video_stream->index;
        break;
      case CODEC_TYPE_AUDIO:
        audio_index = i;
        input_context->streams[i]->discard = AVDISCARD_NONE;
        audio_stream = add_output_stream(output_context, input_context->streams[i]);
	index_map[i] = audio_stream->index;
        break;
      default:
        input_context->streams[i]->discard = AVDISCARD_ALL;
        fprintf(stderr, "segmenter-warning: stream index %d from source woudl be skipped \n", i);
        break;
    }
  }

  if (av_set_parameters(output_context, NULL) < 0) 
  {
    fprintf(stderr, "Segmenter error: Invalid output format parameters\n");
    exit(1);
  }

  dump_format(output_context, 0, config.filename_prefix, 1);

  if(video_index >= 0)
  {
    AVCodec *codec = avcodec_find_decoder(video_stream->codec->codec_id);
    if (!codec) 
    {
      fprintf(stderr, "Segmenter error: Could not find video decoder, key frames will not be honored\n");
    }

    if (avcodec_open(video_stream->codec, codec) < 0) 
    {
      fprintf(stderr, "Segmenter error: Could not open video decoder, key frames will not be honored\n");
    }
  }

  unsigned int output_index = 1;
  snprintf(output_filename, output_filename_size, "%s/%s-%u-%010u.ts", config.temp_directory, config.filename_prefix, config.run_cycle, output_index++);
  if (url_fopen(&output_context->pb, output_filename, URL_WRONLY) < 0) 
  {
    fprintf(stderr, "Segmenter error: Could not open '%s'\n", output_filename);
    exit(1);
  }

  if (av_write_header(output_context)) 
  {
    fprintf(stderr, "Segmenter error: Could not write mpegts header to first output file\n");
    exit(1);
  }

  unsigned int first_segment = 1;
  unsigned int last_segment = 0;
  
  double prev_segment_time = 0;
  double first_segment_time = -1.0;
  int decode_done;
  double segment_time = 0;
  
  unsigned int pktWriteFrameErrorCount = 0;
  do 
  {
    AVPacket packet;

    decode_done = av_read_frame(input_context, &packet);
    if (decode_done < 0) 
    {
      break;
    }

    if (av_dup_packet(&packet) < 0) 
    {
      fprintf(stderr, "Segmenter error: Could not duplicate packet");
      av_free_packet(&packet);
      break;
    }

    if (packet.stream_index == video_index && (packet.flags & PKT_FLAG_KEY)) 
    {
      segment_time = (double)video_stream->pts.val * video_stream->time_base.num / video_stream->time_base.den;
      if (first_segment_time <= 0) 
         fprintf(stderr, "segmenter-debug: received new time from video I frame : %lf\n", segment_time);
    }
    else if (video_index < 0) 
    {
      segment_time = (double)audio_stream->pts.val * audio_stream->time_base.num / audio_stream->time_base.den;
      if (first_segment_time <= 0)
         fprintf(stderr, "segmenter-debug: received new time from audio PTS : %lf\n", segment_time);
    }
    else 
    {
      segment_time = prev_segment_time;
    }

    // initialy previous segment time would be zero, avoid receiving huge difference
    if (prev_segment_time == 0 && segment_time > 0) {
        prev_segment_time = segment_time;
    }

    if (first_segment_time < 0 && segment_time > 0) {
	first_segment_time = segment_time; // this is relative time in MS
    }
    
    //fprintf(stderr, "segmenter-debug: videoPTS=%lf audioPTS=%lf\n", (double)video_stream->pts.val * video_stream->time_base.num / video_stream->time_base.den, (double)audio_stream->pts.val * audio_stream->time_base.num / audio_stream->time_base.den); 
    //fprintf(stderr, "segmenter-debug: cur=%.02lf prev=%.02lf onstartTS=%.02lf first=%.02lf\n", segment_time, prev_segment_time, on_start_timestamp, first_segment_time);

    // timestamps in the streams received from IRDs are relative, 
    // if there's a mismatch - time to restart segmentation process, as entire TS may change
    
    // done writing the current file?
    if (segment_time - prev_segment_time >= config.segment_length) 
    {
      put_flush_packet(output_context->pb);
      url_fclose(output_context->pb);

      output_transfer_command(++last_segment, (segment_time-first_segment_time+on_start_timestamp), (segment_time-prev_segment_time), 0, output_filename);

      snprintf(output_filename, output_filename_size, "%s/%s-%u-%010u.ts", config.temp_directory, config.filename_prefix, config.run_cycle,output_index++);
      if (url_fopen(&output_context->pb, output_filename, URL_WRONLY) < 0) 
      {
        fprintf(stderr, "Segmenter error: Could not open '%s'\n", output_filename);
        break;
      }

      prev_segment_time = segment_time;
    }
    
    
    // because indicies from original and destination packets differ, perform correction
    if (index_map[packet.stream_index] < 0) {
       ret = -1;
    }else {
  	packet.stream_index = index_map[packet.stream_index];
    	ret = av_interleaved_write_frame(output_context, &packet);
    }

    av_free_packet(&packet);
    
    if (ret < 0) 
    {
      pktWriteFrameErrorCount ++;
      if (first_segment_time > 0 && pktWriteFrameErrorCount > PKT_WRITE_FRAME_ERROR_LIMIT) {
          fprintf(stderr, "segmenter-error: can't handle last %u packets. requesting process restart.");
          break;
      }
    }
    else if (ret > 0) 
    {
      fprintf(stderr, "Segmenter info: End of stream requested\n");
      av_free_packet(&packet);
      break;
    }else{
      pktWriteFrameErrorCount = 0; // clear av_interleaved_write_frame() error count
    }
  } while (!decode_done);

  av_write_trailer(output_context);

  if (video_index >= 0) 
  {
    avcodec_close(video_stream->codec);
  }

  for(i = 0; i < output_context->nb_streams; i++) 
  {
    av_freep(&output_context->streams[i]->codec);
    av_freep(&output_context->streams[i]);
  }

  url_fclose(output_context->pb);
  av_free(output_context);
  av_close_input_file(input_context);

      output_transfer_command(++last_segment, (segment_time-first_segment_time+on_start_timestamp), (segment_time-prev_segment_time), 1, output_filename);
  return 0;
}

int main(int argc, char **argv)
{
  if(argc != 5)
  {
    fprintf(stderr, "Usage: %s <segment length> <output location> <filename prefix> <encoding profile>\n", argv[0]);
    return 1;
  }

  struct config_info config;

  memset(&config, 0, sizeof(struct config_info));

  config.segment_length = atoi(argv[1]); 
  config.temp_directory = argv[2];
  config.filename_prefix = argv[3];
  config.encoding_profile = argv[4];
  config.input_filename = "pipe://1";
  config.start_from_segment = 0;
  config.run_cycle = 1;

  while (1) 
  {
	int ret = segment_process(config);
	if (ret < 0) {
		fprintf(stderr, "segmenter-fatal: need restart");
		exit(ret);
	}
	config.run_cycle++;
	config.start_from_segment+=100; // this would be handled by discontinuity on client
  }
}
