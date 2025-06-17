import axiosplus from "@/scripts/utils/axios.js";

/**
 * 开始执行任务队列
 * @return {Promise<AxiosResponse<any, any>>}
 */
function start_task_queue() {
  return axiosplus.get("/api/start");
}

/**
 * 终止执行任务队列
 * @return {Promise<AxiosResponse<any, any>>}
 */
function stop_task_queue() {
  return axiosplus.get("/api/stop");
}

/**
 * 获取后端状态
 * @return {Promise<AxiosResponse<any, any>>}
 */
function get_status() {
  return axiosplus.get("/api/status");
}

/**
 * 获取所有已注册的任务
 * @return {Promise<AxiosResponse<any, any>>}
 */
function get_registered_tasks() {
  return axiosplus.get("/api/get_registered_tasks")
}

/**
 * 禁用任务
 * @param task_name
 * @return {Promise<axios.AxiosResponse<any>>}
 */
function disable_task(task_name) {
  return axiosplus.post(`/api/disable_task/${task_name}`);
}

function enable_task(task_name) {
  return axiosplus.post(`/api/enable_task/${task_name}`);
}

function switch_yolo_model(model_name) {
  return axiosplus.get(`/api/switch_yolo_model/${model_name}`);
}

export default {
  start_task_queue,
  stop_task_queue,
  get_status,
  get_registered_tasks,
  disable_task,
  enable_task,
  switch_yolo_model,
}
